"""
Les deux enchaînements exécutés par la file de travail (voir queue.py,
jobs.py) : analyse d'un commit puis décision, et déploiement d'un commit
approuvé. Appelés uniquement par les jobs, jamais par une route.
"""
import logging
from typing import Optional

from sqlmodel import Session

from app.core.database import db_manager
from app.decision_engine import evaluate_pipeline_and_decide
from app.domain.decision import UNVERIFIABLE, Decision, DeploymentOutcome
from app.domain.pipeline_status import PipelineStatus
from app.models.audit import AuditLog, append_audit_log
from app.models.pipeline import Pipeline, append_pipeline_log
from app.orchestration.tasks import (
    ensure_build_pushed,
    run_sonarqube_scan,
    trigger_argocd_sync,
    trigger_jenkins_build,
    verify_deployed_image,
    write_release_manifest,
)

logger = logging.getLogger(__name__)


async def security_analysis_flow(
    pipeline_id: Optional[int],
    repository: str,
    commit_hash: str,
    author: str,
    ai_metadata: dict,
    identity_source: Optional[str] = None,
) -> str:
    """
    Attend "Build & Test" côté Jenkins, puis l'analyse SonarQube de ce
    commit (le scan tourne après le build dans le Jenkinsfile généré, donc
    les deux attentes sont séquentielles par construction), puis le Moteur
    de décision tranche et déclenche lui-même le déploiement si autorisé.

    Aucune exception ne sort d'ici : une panne réseau qui épuise les
    tentatives laisserait sinon le pipeline en PENDING sans trace.
    """
    try:
        return await _run_analysis(pipeline_id, repository, commit_hash, author, ai_metadata, identity_source)
    except Exception as e:
        with Session(db_manager.engine) as session:
            append_pipeline_log(session, pipeline_id, f"Échec inattendu du workflow d'analyse : {e}")
            pipeline = session.get(Pipeline, pipeline_id) if pipeline_id else None
            if pipeline:
                pipeline.status = PipelineStatus.ANALYSIS_FAILED.value
                session.add(pipeline)
                session.commit()
        logger.warning(f"Analyse en échec pour le pipeline #{pipeline_id} : {e}")
        return PipelineStatus.ANALYSIS_FAILED.value


async def _run_analysis(
    pipeline_id: Optional[int], repository: str, commit_hash: str, author: str, ai_metadata: dict, identity_source: Optional[str]
) -> str:
    with Session(db_manager.engine) as session:
        append_pipeline_log(session, pipeline_id, f"Analyse démarrée pour {repository} ({commit_hash[:7]}).")

    # Une étape qui épuise ses tentatives (Jenkins/SonarQube durablement
    # injoignables) vaut un échec, pas un abandon du pipeline.
    try:
        build_result = await trigger_jenkins_build(repository, commit_hash, pipeline_id)
    except Exception:  # noqa: BLE001 : déjà journalisé par step()
        build_result = {"success": False, "build_number": None}

    # Build en échec : Jenkins s'arrête là, aucun scan ne viendra. Inutile
    # d'attendre 10 minutes une analyse qui n'existera jamais, la décision
    # bloque de toute façon sur le build.
    if build_result.get("success"):
        try:
            scan_result = await run_sonarqube_scan(repository, commit_hash)
        except Exception:  # noqa: BLE001
            scan_result = {"vulnerabilities": UNVERIFIABLE, "bugs": UNVERIFIABLE}
    else:
        scan_result = {"vulnerabilities": UNVERIFIABLE, "bugs": UNVERIFIABLE, "analysis_missing": True}

    with Session(db_manager.engine) as session:
        if pipeline_id and build_result.get("build_number") is not None:
            pipeline = session.get(Pipeline, pipeline_id)
            if pipeline:
                pipeline.jenkins_build_number = build_result["build_number"]
                session.add(pipeline)
                session.commit()

        append_pipeline_log(
            session, pipeline_id,
            f"Build Jenkins : {'succès' if build_result.get('success') else 'échec'}.",
        )
        if scan_result.get("analysis_missing"):
            append_pipeline_log(session, pipeline_id, "Analyse SonarQube : aucune analyse attribuable à ce commit.")
        else:
            append_pipeline_log(
                session, pipeline_id,
                f"Analyse SonarQube : {scan_result.get('vulnerabilities', '?')} vulnérabilité(s), "
                f"{scan_result.get('bugs', '?')} bug(s).",
            )

        audit_entry = await evaluate_pipeline_and_decide(
            session,
            repository=repository,
            commit_hash=commit_hash,
            author=author,
            ai_metadata=ai_metadata,
            sonar_metrics=scan_result,
            build_success=bool(build_result.get("success")),
            identity_source=identity_source,
        )

        pipeline = session.get(Pipeline, pipeline_id) if pipeline_id else None
        if pipeline:
            # AUTO_AUTH -> "DEPLOYING", jamais "APPROVED"/"DEPLOYED" directement :
            # deployment_flow() est appelé juste après et seul lui sait si le
            # déploiement a réellement abouti (voir plus bas).
            pipeline.status = {
                Decision.AUTO_AUTH.value: PipelineStatus.DEPLOYING.value,
                Decision.BLOCKED.value: PipelineStatus.BLOCKED.value,
                Decision.WAITING_HUMAN.value: PipelineStatus.WAITING_HUMAN.value,
            }.get(audit_entry.decision, pipeline.status)
            session.add(pipeline)
            session.commit()

        append_pipeline_log(session, pipeline_id, f"Décision : {audit_entry.decision} : {audit_entry.justification}")

        # Capturé avant la fermeture de la session : au-delà de ce bloc,
        # audit_entry est détaché et relire ses attributs lève une
        # DetachedInstanceError (SQLAlchemy recharge paresseusement).
        decision = audit_entry.decision
        audit_id = audit_entry.id

    if decision == "AUTO_AUTH":
        # Job séparé : un redémarrage entre la décision et le déploiement ne
        # perd ni l'une ni l'autre.
        from app.orchestration.jobs import enqueue_deployment

        await enqueue_deployment(pipeline_id, repository, commit_hash, audit_id)

    return decision


def _seal_outcome(
    session: Session,
    pipeline: Optional[Pipeline],
    repository: str,
    commit_hash: str,
    outcome: DeploymentOutcome,
    detail: str,
) -> None:
    """
    Inscrit l'issue du déploiement dans le journal scellé.

    Le journal ne prouvait que la décision : « autorisé le 12 à 14 h » était
    scellé, « déployé » ne l'était pas. L'entrée reprend le développeur et le
    dépôt du pipeline pour que l'acte se relise à côté du verdict qui l'a
    permis. Un échec d'écriture ici ne fait pas échouer le déploiement :
    l'état du cluster prime, mais il est journalisé bruyamment.
    """
    try:
        append_audit_log(
            session,
            AuditLog(
                developer_username=pipeline.author if pipeline else "inconnu",
                developer_identity_source=pipeline.identity_source if pipeline else None,
                repository_name=repository,
                commit_hash=commit_hash,
                decision=outcome.value,
                justification=(
                    f"Déploiement réussi : {detail}." if outcome is DeploymentOutcome.DEPLOYED
                    else f"Déploiement en échec : {detail}"
                ),
            ),
        )
    except Exception as e:  # noqa: BLE001 - le cluster fait foi, la trace ne doit pas l'annuler
        logger.error("Issue de déploiement non journalisée pour %s (%s) : %s", repository, commit_hash[:7], e)


async def deployment_flow(
    pipeline_id: Optional[int], repository: str, commit_hash: str, audit_id: Optional[int] = None
) -> bool:
    """
    Écriture GitOps : le SHA approuvé est commité dans le manifeste du dépôt,
    Argo CD synchronise cette révision précise, et DEPLOYED n'est posé
    qu'une fois l'image du commit observée sur l'application. Chaque
    étape qui échoue arrête tout et laisse sa raison dans le journal du
    pipeline : un statut DEPLOYED qui ne correspond à rien sur le cluster
    est pire qu'un échec.

    N'est appelé que depuis le Moteur de décision (ce flow lui-même après
    AUTO_AUTH, ou routes_decisions.approve_pipeline après une dérogation),
    jamais depuis une route publique : il n'existe aucun autre chemin vers
    le manifeste ni vers Argo CD, c'est ce qui tient le fail-closed.

    Avant d'écrire quoi que ce soit, il faut une image pour ce commit (voir
    ensure_build_pushed) : Jenkins ne construit plus inconditionnellement,
    le premier passage a pu s'arrêter à la vérification de sécurité (cas
    d'une dérogation accordée après coup).
    """

    def _fail(reason: str) -> bool:
        with Session(db_manager.engine) as session:
            append_pipeline_log(session, pipeline_id, f"Déploiement annulé : {reason}")
            pipeline = session.get(Pipeline, pipeline_id) if pipeline_id else None
            if pipeline:
                pipeline.status = PipelineStatus.DEPLOY_FAILED.value
                session.add(pipeline)
                session.commit()
            _seal_outcome(session, pipeline, repository, commit_hash, DeploymentOutcome.FAILED, reason)
        return False

    def _log(message: str) -> None:
        with Session(db_manager.engine) as session:
            append_pipeline_log(session, pipeline_id, message)

    try:
        with Session(db_manager.engine) as session:
            append_pipeline_log(session, pipeline_id, f"Déploiement démarré pour {repository} ({commit_hash[:7]}).")
            pipeline = session.get(Pipeline, pipeline_id) if pipeline_id else None
            existing_build_number = pipeline.jenkins_build_number if pipeline else None

        try:
            build_pushed = await ensure_build_pushed(repository, commit_hash, existing_build_number, pipeline_id)
        except Exception as e:
            logger.warning(f"Échec de l'obtention d'un build poussé : {e}")
            build_pushed = False
        if not build_pushed:
            return _fail("impossible d'obtenir une image construite et poussée pour ce commit.")

        try:
            release = await write_release_manifest(repository, commit_hash, audit_id)
        except Exception as e:
            release = {"error": str(e)}
        if release.get("error"):
            return _fail(release["error"])
        if release.get("unchanged"):
            _log("Manifeste déjà épinglé sur ce commit, synchronisation de la tête de branche.")
        else:
            _log(f"Manifeste commité ({release['revision'][:7]}) : image {release['image_ref']}.")

        try:
            synced = await trigger_argocd_sync(repository, release.get("revision"))
        except Exception as e:
            logger.warning(f"Échec de la synchronisation Argo CD : {e}")
            synced = False
        if not synced:
            return _fail("synchronisation Argo CD en échec ou hors délai.")
        _log("Synchronisation Argo CD : succès.")

        try:
            running = await verify_deployed_image(repository, release["image_ref"])
        except Exception as e:
            logger.warning(f"Échec de la vérification d'image : {e}")
            running = False
        if not running:
            return _fail(f"synchronisée, mais l'image {release['image_ref']} n'est pas observée sur l'application Argo CD.")

        with Session(db_manager.engine) as session:
            append_pipeline_log(session, pipeline_id, f"Déployé : {release['image_ref']} observée sur le cluster.")
            pipeline = session.get(Pipeline, pipeline_id) if pipeline_id else None
            if pipeline:
                pipeline.status = PipelineStatus.DEPLOYED.value
                session.add(pipeline)
                session.commit()
            _seal_outcome(
                session, pipeline, repository, commit_hash, DeploymentOutcome.DEPLOYED,
                f"image {release['image_ref']} observée sur l'application Argo CD"
                + (f", révision {release['revision'][:7]}" if release.get("revision") else ""),
            )
        return True
    except Exception as e:
        logger.warning(f"Déploiement en échec pour le pipeline #{pipeline_id} : {e}")
        return False
