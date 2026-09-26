"""
Étapes d'un job (build, analyse, écriture du manifeste, synchronisation) :
chaque fonction appelle un client de service, avec ses propres tentatives
et son délai (voir step). Un échec définitif remonte en exception ; c'est
le flow qui décide quoi en faire.
"""
import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable

from sqlmodel import Session
from tenacity import AsyncRetrying, RetryError, stop_after_attempt, wait_fixed

from app.core.database import db_manager
from app.domain.manifest import ManifestError, pin_image
from app.models.pipeline import Pipeline
from app.providers import provider_for
from app.services.argocd_client import ArgoCDClient
from app.services.jenkins_client import JenkinsClient
from app.services.pipeline_config import (
    get_pipeline_config,
    parse_repo_slug,
    resolve_argocd_app,
    resolve_docker_image,
    resolve_git_branch,
    resolve_jenkins_job,
    resolve_manifest_path,
    resolve_sonarqube_key,
)
from app.services.sonarqube_client import UNMEASURED, SonarQubeClient

logger = logging.getLogger(__name__)


def step(name: str, *, retries: int = 0, delay: float = 10, timeout: float = 900):
    """Réessaie sur exception, jamais sur un résultat "faux" ; chaque tentative est bornée par `timeout`."""

    def wrap(fn: Callable[..., Awaitable]):
        @functools.wraps(fn)
        async def run(*args, **kwargs):
            try:
                async for attempt in AsyncRetrying(stop=stop_after_attempt(retries + 1), wait=wait_fixed(delay), reraise=True):
                    with attempt:
                        return await asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)
            except RetryError as e:  # reraise=True : ne devrait pas arriver, garde-fou
                raise e.last_attempt.exception() from e
            except Exception as e:
                logger.warning(f"Étape « {name} » en échec après {retries + 1} tentative(s) : {e}")
                raise

        return run

    return wrap


@step("Build Jenkins", retries=2, delay=10, timeout=900)
async def trigger_jenkins_build(repository: str, commit_hash: str, pipeline_id: int | None = None) -> dict:
    """Renvoie {"success": bool, "build_number": Optional[int]}."""
    with Session(db_manager.engine) as session:
        try:
            jenkins = JenkinsClient(session)
        except ValueError:
            return {"success": False, "build_number": None}
        job_name = resolve_jenkins_job(get_pipeline_config(session, repository), repository)

        async def _save_build_number(build_number: int) -> None:
            # Enregistré dès que connu, bien avant la fin de "Build & Test" -
            # sans ça, la page de détail d'un pipeline affiche "aucun build
            # associé" pendant plusieurs minutes alors que Jenkins tourne déjà.
            if pipeline_id is None:
                return
            pipeline = session.get(Pipeline, pipeline_id)
            if pipeline:
                pipeline.jenkins_build_number = build_number
                session.add(pipeline)
                session.commit()

        return await jenkins.trigger_build_and_wait(
            job_name=job_name, commit_hash=commit_hash, on_build_number=_save_build_number
        )


@step("Analyse SonarQube", retries=2, delay=10, timeout=900)
async def run_sonarqube_scan(repository: str, commit_hash: str) -> dict:
    """
    Lit les métriques SonarQube de CE commit. Appelé une fois "Build & Test"
    terminé côté Jenkins, puisque c'est après cette étape que sonar-scanner
    tourne (voir services/scaffold.py) : lancer l'attente plus tôt, c'est
    dépenser le budget d'attente pendant le build. Si l'analyse n'apparaît
    pas, ou si une analyse plus récente l'a recouverte, on renvoie
    UNVERIFIABLE et la décision part en WAITING_HUMAN.
    """
    with Session(db_manager.engine) as session:
        try:
            sonar = SonarQubeClient(session)
        except ValueError:
            return dict(UNMEASURED)
        project_key = resolve_sonarqube_key(get_pipeline_config(session, repository), repository)
        if not await sonar.wait_for_analysis(project_key=project_key, commit_hash=commit_hash):
            return {**UNMEASURED, "analysis_missing": True}
        # Les deux lectures accompagnent toujours la décision, quel que soit le
        # critère retenu : l'entrée d'audit garde ainsi l'image complète de ce
        # que SonarQube disait au moment du verdict, pas seulement le chiffre
        # qui a tranché.
        metrics = await sonar.get_security_metrics(project_key=project_key)
        return {**metrics, **await sonar.get_quality_gate(project_key=project_key)}


@step("Build poussé", retries=1, delay=10, timeout=900)
async def ensure_build_pushed(
    repository: str, commit_hash: str, existing_build_number: int | None, pipeline_id: int | None = None
) -> bool:
    """
    S'assure qu'une image taguée par ce commit existe dans le registre avant
    de la promouvoir (voir promote_docker_tag), deux cas selon comment on
    en arrive à un déploiement :
    - AUTO_AUTH : le job Jenkins déclenché pendant l'analyse est encore en
      cours (il vient de recevoir le feu vert à sa propre étape de
      vérification de sécurité), on attend juste qu'il finisse.
    - Dérogation accordée plus tard : ce même job s'était arrêté (refusé) à
      cette étape, sans rien construire, on en redéclenche un ; cette fois
      la vérification passera (décision déjà favorable), donc on attend le
      job entier plutôt que seulement "Build & Test".
    """
    with Session(db_manager.engine) as session:
        try:
            jenkins = JenkinsClient(session)
        except ValueError:
            return False
        job_name = resolve_jenkins_job(get_pipeline_config(session, repository), repository)

        if existing_build_number is not None:
            status = await jenkins.get_job_status(job_name, existing_build_number)
            if status["building"]:
                return await jenkins.wait_for_build_completion(job_name, existing_build_number)
            if status["result"] == "SUCCESS":
                return True
            # Terminé sans succès (refusé à la vérification, ou échec réel) : on redéclenche ci-dessous.

        async def _save_build_number(build_number: int) -> None:
            # Sinon la fiche du pipeline montre encore les étapes du build
            # précédent alors qu'un nouveau tourne déjà.
            if pipeline_id is None:
                return
            pipeline = session.get(Pipeline, pipeline_id)
            if pipeline:
                pipeline.jenkins_build_number = build_number
                session.add(pipeline)
                session.commit()

        result = await jenkins.trigger_build_and_wait(
            job_name=job_name, commit_hash=commit_hash, wait_for_stage=None, on_build_number=_save_build_number
        )
        return bool(result.get("success"))


@step("Écriture du manifeste", retries=1, delay=5, timeout=60)
async def write_release_manifest(repository: str, commit_hash: str, audit_id: int | None) -> dict:
    """
    Écriture GitOps : épingle l'image du manifeste sur le SHA approuvé et
    commite dans le dépôt, sur la branche que suit Argo CD. Renvoie
    {"revision": sha du commit de manifeste, "image_ref": "image:sha"} ou
    {"error": raison}. Chaque prérequis manquant est une raison explicite
    dans le journal du pipeline, jamais un déploiement "au mieux".
    """
    with Session(db_manager.engine) as session:
        config = get_pipeline_config(session, repository)
        kind = config.vcs_provider if config and config.vcs_provider else "gitea"
        try:
            forge = provider_for(session, kind)
        except ValueError:
            return {"error": f"La forge {kind} n'est pas configurée (page Intégrations) : impossible d'écrire le manifeste."}
        slug = parse_repo_slug(config.git_repo_url if config else None)
        if not slug:
            return {"error": "URL du dépôt absente ou illisible dans la configuration du pipeline."}
        owner, repo = slug
        branch = resolve_git_branch(config)
        path = resolve_manifest_path(config)
        image = resolve_docker_image(config, repository)

    try:
        current = await forge.get_file(owner, repo, path, branch)
        pinned = pin_image(current["content"], image, commit_hash)
    except ManifestError as e:
        return {"error": f"Manifeste {path} : {e}."}
    except Exception as e:
        return {"error": str(e)}

    image_ref = f"{image}:{commit_hash}"
    if pinned == current["content"]:
        # Déjà épinglé (relance d'un déploiement) : rien à commiter, on
        # synchronise la tête de branche.
        return {"revision": None, "image_ref": image_ref, "unchanged": True}

    message = f"deploy: {repository} {commit_hash[:7]} [skip ci]" + chr(10) * 2
    message += f"Manifeste épinglé sur {commit_hash} après décision favorable"
    message += f" (audit #{audit_id})." if audit_id else "."
    try:
        revision = await forge.update_file(owner, repo, path, branch, pinned, current["sha"], message)
    except Exception as e:
        return {"error": str(e)}
    return {"revision": revision, "image_ref": image_ref}


@step("Synchronisation Argo CD", retries=1, delay=10, timeout=300)
async def trigger_argocd_sync(repository: str, revision: str | None = None) -> bool:
    """Déclenché uniquement après autorisation du Moteur de décision (principe fail-closed)."""
    with Session(db_manager.engine) as session:
        try:
            argocd = ArgoCDClient(session)
        except ValueError:
            return False
        app_name = resolve_argocd_app(get_pipeline_config(session, repository), repository)
        return await argocd.sync_application(app_name=app_name, revision=revision)


@step("Preuve de déploiement", retries=0, timeout=360)
async def verify_deployed_image(repository: str, image_ref: str) -> bool:
    """DEPLOYED n'est posé qu'une fois l'image du commit observée sur l'application Argo CD."""
    with Session(db_manager.engine) as session:
        try:
            argocd = ArgoCDClient(session)
        except ValueError:
            return False
        app_name = resolve_argocd_app(get_pipeline_config(session, repository), repository)
        return await argocd.wait_for_image(app_name=app_name, image_ref=image_ref)
