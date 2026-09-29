import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlmodel import Session, select

from app.core.database import db_manager, get_session
from app.core.deps import API_TOKEN_PREFIX_IDENTITY, get_current_user, require_module, require_roles
from app.domain.decision import OUTCOME_VALUES
from app.domain.pipeline_status import PipelineStatus
from app.models.audit import AuditLog, append_audit_log
from app.models.pipeline import Pipeline, start_pipeline_run
from app.models.pipeline_config import PipelineConfig
from app.models.user import User, UserRole
from app.orchestration.jobs import defer_analysis, defer_deployment
from app.services.jenkins_client import JenkinsClient
from app.services.notifier import notify_derogation_granted

logger = logging.getLogger(__name__)

router = APIRouter()


def _find_pipeline(db: Session, repository: str, commit_hash: str) -> Optional[Pipeline]:
    # Toujours (dépôt, commit) : un même hash existe sur plusieurs dépôts
    # (le commit factice de "Tester l'envoi", entre autres), voir models/pipeline.py.
    return db.exec(
        select(Pipeline)
        .where(Pipeline.repository == repository, Pipeline.commit_id == commit_hash)
        .order_by(Pipeline.id.desc())  # type: ignore[arg-type]
    ).first()


GATE_MAX_WAIT_SECONDS = 300
_GATE_ALLOW = ("AUTO_AUTH", "DEROGATION")
# WAITING_HUMAN et DEROGATION_* refusent tout de suite : personne ne validera
# dans le temps du sondage, et garder l'agent Jenkins occupé n'y changerait
# rien. Une dérogation accordée plus tard redéclenche elle-même un build.
_GATE_DENY = (
    "BLOCKED",
    "REJECTED_INVALID_SIGNATURE",
    "REJECTED_UNREGISTERED_REPOSITORY",
    "WAITING_HUMAN",
    "DEROGATION_REQUESTED",
    "DEROGATION_PENDING",
)


@router.get("/gate/{repository}/{commit_hash}")
async def gate_check(
    repository: str = Path(..., max_length=255),
    commit_hash: str = Path(..., min_length=7, max_length=64, pattern=r"^[0-9a-fA-F]+$"),
    wait: int = Query(default=240, ge=1, le=300),
    _: User = Depends(get_current_user),
):
    """
    Point de contrôle appelé par Jenkins avant de construire l'image. 200
    uniquement sur AUTO_AUTH ou DEROGATION ; tout le reste (attente, blocage,
    pas de décision dans le délai) fait échouer le job : fail-closed.
    """
    # Une connexion n'est prise que le temps de chaque lecture, jamais pendant
    # tout le sondage : quinze jobs Jenkins en attente ne vident plus le pool.
    # Le plafond de 300 s couvre le cas nominal (l'analyse SonarQube d'un
    # commit) ; au-delà, Jenkins échoue et un humain regarde.
    deadline = time.monotonic() + max(1, min(wait, GATE_MAX_WAIT_SECONDS))

    while True:
        with Session(db_manager.engine) as db:
            # Les issues de déploiement partagent la chaîne mais ne sont pas
            # des verdicts : sans ce filtre, un commit déjà déployé n'aurait
            # plus de décision lisible et le point de contrôle expirerait.
            latest = db.exec(
                select(AuditLog.decision)
                .where(
                    AuditLog.repository_name == repository,
                    AuditLog.commit_hash == commit_hash,
                    AuditLog.decision.not_in(OUTCOME_VALUES),  # type: ignore[union-attr]
                )
                .order_by(AuditLog.id.desc())  # type: ignore[arg-type]
            ).first()

        if latest in _GATE_ALLOW:
            return {"allow": True, "decision": latest}
        if latest in _GATE_DENY:
            raise HTTPException(status_code=403, detail=f"Décision '{latest}' : construction non autorisée.")

        if time.monotonic() > deadline:
            raise HTTPException(status_code=408, detail="Décision de sécurité indisponible avant le délai.")
        await asyncio.sleep(3)


# --- Consommé par le Dashboard / le CLI ---
@router.get("/repositories")
def list_repositories(
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """
    Noms des dépôts enregistrés (pas leurs réglages, pas leur secret), pour
    le sélecteur "Tous les dépôts / un dépôt précis" du tableau de bord.
    Accessible à tous les rôles, contrairement à /api/pipeline-configs
    (réservé aux admins) : connaître la simple LISTE des projets existants
    n'est pas sensible, contrairement à leurs réglages.
    """
    configs = db.exec(select(PipelineConfig).order_by(PipelineConfig.repository)).all()  # type: ignore[arg-type]
    return [{"repository": c.repository} for c in configs]


@router.get("/pipelines")
def list_pipelines(
    repository: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200, description="Nombre de pipelines par page."),
    offset: int = Query(default=0, ge=0, description="Décalage pour la pagination."),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    Un développeur consulte l'état de SES pipelines (filtré sur son propre
    nom d'auteur Gitea) ; administrateur/responsable sécurité/direction
    supervisent l'ensemble des projets.

    `repository` (optionnel) : restreint à un seul dépôt enregistré, le
    sélecteur "Tous les dépôts / dépôt précis" du tableau de bord.

    Paginé : `limit` (max 200) et `offset`. Sans pagination, une instance
    avec des milliers de pipelines renverrait plusieurs mégaoctets par appel.
    """
    query = select(Pipeline).order_by(Pipeline.id.desc())  # type: ignore[arg-type]
    if user.role == UserRole.DEVELOPER:
        query = query.where(Pipeline.author == user.username)
    if repository:
        query = query.where(Pipeline.repository == repository)

    total = db.exec(select(func.count()).select_from(query.subquery())).one()
    pipelines = db.exec(query.offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset, "items": pipelines}


@router.get("/pipelines/{pipeline_id}")
def get_pipeline(
    pipeline_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Un pipeline précis, même règle de visibilité que la liste."""
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline or (user.role == UserRole.DEVELOPER and pipeline.author != user.username):
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    return pipeline


@router.get("/summary")
def get_summary(
    repository: Optional[str] = None,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    Compteurs des tuiles du tableau de bord, agrégés en SQL (GROUP BY) : on
    ne rapatrie jamais les lignes pour les compter en Python. Même filtrage
    par rôle et par dépôt que /pipelines.
    """
    pipeline_query = select(Pipeline.status, func.count()).group_by(Pipeline.status)
    audit_query = select(AuditLog.decision, func.count()).group_by(AuditLog.decision)
    if user.role == UserRole.DEVELOPER:
        pipeline_query = pipeline_query.where(Pipeline.author == user.username)
        audit_query = audit_query.where(AuditLog.developer_username == user.username)
    if repository:
        pipeline_query = pipeline_query.where(Pipeline.repository == repository)
        audit_query = audit_query.where(AuditLog.repository_name == repository)

    status_counts = {status: count for status, count in db.exec(pipeline_query).all()}
    return {
        "pipelines_total": sum(status_counts.values()),
        "pipeline_status_counts": status_counts,
        "decision_counts": {decision: count for decision, count in db.exec(audit_query).all()},
    }


_TERMINAL_BLOCKED = {"BLOCKED", "REJECTED_INVALID_SIGNATURE"}


@router.get("/activity")
def get_activity(
    days: int = Query(default=365, ge=1, le=366),
    repository: Optional[str] = None,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    Volume quotidien de pipelines sur les `days` derniers jours, alimente le
    calendrier d'activité du tableau de bord.

    Agrégé en SQL (`GROUP BY` par jour) : sur un an d'historique, charger
    toutes les lignes pour les compter en Python coûterait plusieurs
    mégaoctets par affichage. Même filtrage par rôle que /pipelines.
    Les jours sans activité sont absents de la réponse ; le client les
    complète à zéro.
    """
    since = datetime.now(timezone.utc).date() - timedelta(days=days - 1)

    # Colonne TIMESTAMPTZ : tronquée en UTC explicitement, sinon PostgreSQL
    # utilise le fuseau de la session et un push de 23h30 glisse au lendemain.
    day = func.date(func.timezone("UTC", Pipeline.created_at)).label("day")

    query = (
        select(
            day,
            func.count().label("total"),
            func.count(case((Pipeline.status == PipelineStatus.DEPLOYED.value, 1))).label("deployed"),
            func.count(case((Pipeline.status.in_(_TERMINAL_BLOCKED), 1))).label("blocked"),  # type: ignore[attr-defined]
        )
        .where(Pipeline.created_at >= since)  # type: ignore[arg-type]
        .group_by(day)
        .order_by(day)
    )
    if user.role == UserRole.DEVELOPER:
        query = query.where(Pipeline.author == user.username)
    if repository:
        query = query.where(Pipeline.repository == repository)

    return [
        {"date": row.day.isoformat(), "total": row.total, "deployed": row.deployed, "blocked": row.blocked}
        for row in db.exec(query).all()
    ]


@router.get("/pipelines/{pipeline_id}/logs", dependencies=[Depends(require_module("pipelines"))])
async def get_pipeline_logs(
    pipeline_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    Consulter les journaux d'exécution. La console Jenkins est allée
    chercher en direct auprès de Jenkins (via le numéro de build conservé) ;
    le déroulé de l'analyse et du déploiement vient de `execution_log`, la
    narration que Hadi écrit lui-même au fil de son propre
    workflow interne (plus de service d'orchestration séparé à interroger).
    """
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    if user.role == UserRole.DEVELOPER and pipeline.author != user.username:
        raise HTTPException(status_code=403, detail="Ce pipeline ne vous appartient pas.")

    jenkins_console: Optional[str] = None
    stages: list = []
    notes: list[str] = []

    if pipeline.jenkins_build_number is not None:
        try:
            jenkins = JenkinsClient(db)
            jenkins_console = await jenkins.get_console_text(pipeline.repository, pipeline.jenkins_build_number)
            stages = await jenkins.get_stages(pipeline.repository, pipeline.jenkins_build_number)
        except Exception as e:
            notes.append(f"Console Jenkins indisponible : {e}")
    else:
        notes.append("Aucun build Jenkins encore associé à ce pipeline.")

    if not pipeline.execution_log:
        notes.append("Le workflow interne n'a pas encore produit de journal pour ce pipeline.")

    return {
        "pipeline_id": pipeline.id,
        "jenkins_console": jenkins_console,
        "stages": stages,
        "execution_log": pipeline.execution_log,
        "notes": notes,
    }


@router.get("/pipelines/{pipeline_id}/stages", dependencies=[Depends(require_module("pipelines"))])
async def get_pipeline_stages(
    pipeline_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    Étapes du build Jenkins, et rien d'autre.

    Séparé de /logs volontairement : suivre une exécution en direct veut dire
    redemander les étapes toutes les deux ou trois secondes, alors que la
    console peut peser plusieurs centaines de kilo-octets. Les deux au même
    rythme, c'était soit un affichage en retard, soit Jenkins saturé par des
    consoles rapatriées en boucle.
    """
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    if user.role == UserRole.DEVELOPER and pipeline.author != user.username:
        raise HTTPException(status_code=403, detail="Ce pipeline ne vous appartient pas.")

    stages: list = []
    if pipeline.jenkins_build_number is not None:
        try:
            stages = await JenkinsClient(db).get_stages(pipeline.repository, pipeline.jenkins_build_number)
        except Exception as e:
            # L'affichage des étapes ne doit jamais faire échouer la page :
            # la même erreur est déjà remontée en détail par /logs.
            logger.debug("Étapes Jenkins indisponibles pour le pipeline %s : %s", pipeline_id, e)

    return {
        "pipeline_id": pipeline.id,
        "status": pipeline.status,
        "jenkins_build_number": pipeline.jenkins_build_number,
        "stages": stages,
    }


@router.post("/pipelines/{pipeline_id}/retrigger", dependencies=[Depends(require_module("pipelines"))])
async def retrigger_pipeline(
    pipeline_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    Relance l'analyse complète (Jenkins + SonarQube + décision) pour un
    pipeline déjà existant, sur le même commit, pensé pour un échec
    d'infrastructure (dépendance introuvable côté agent Jenkins, service
    externe injoignable...) qui n'a rien à voir avec le code lui-même, sans
    avoir à repousser un commit vide juste pour redéclencher une analyse.
    Un développeur ne peut relancer que SES PROPRES pipelines ; admin/
    responsable sécurité peuvent relancer n'importe lequel.
    """
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    if user.role == UserRole.DEVELOPER and pipeline.author != user.username:
        raise HTTPException(status_code=403, detail="Ce pipeline ne vous appartient pas.")

    start_pipeline_run(db, pipeline, f"relance demandée par {user.username}")

    captured_repository = pipeline.repository
    captured_commit_hash = pipeline.commit_id
    captured_author = pipeline.author
    captured_branch = pipeline.branch

    # Le payload Webhook d'origine (fichiers modifiés, nombre de commits...)
    # n'est jamais conservé tel quel, l'IA retombe ici sur des métadonnées
    # neutres, comme pour un push sans particularité détectable, plutôt que
    # d'inventer des valeurs. Le score reste tracé, jamais décisionnel seul.
    ai_metadata = {
        "branch": captured_branch,
        "commit_count": 1,
        "files_changed": 0,
        "changed_file_paths": [],
        "hour_of_day": datetime.now(timezone.utc).hour,
    }

    defer_analysis(pipeline_id, captured_repository, captured_commit_hash, captured_author, ai_metadata)

    return {
        "status": "success",
        "message": f"Relance déclenchée pour {captured_repository} ({captured_commit_hash[:7]}).",
        "pipeline_id": pipeline_id,
    }


# Décisions sur lesquelles un administrateur peut encore agir, tant qu'aucune
# dérogation effective ne les a remplacées.
_ACTIONABLE_DECISIONS = ("WAITING_HUMAN", "BLOCKED", "DEROGATION_REQUESTED", "DEROGATION_PENDING")


def _non_superseded(db: Session, entries: list[AuditLog]) -> list[AuditLog]:
    superseded_ids = {
        row for row in db.exec(select(AuditLog.supersedes_audit_id).where(AuditLog.supersedes_audit_id.is_not(None)))
    }
    return [entry for entry in entries if entry.id not in superseded_ids]


@router.get("/pending", dependencies=[Depends(require_module("decisions"))])
def list_pending(
    repository: Optional[str] = None,
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    """File des pipelines nécessitant une action d'un administrateur."""
    query = select(AuditLog).where(AuditLog.decision.in_(_ACTIONABLE_DECISIONS)).order_by(AuditLog.id.desc())  # type: ignore[arg-type]
    if repository:
        query = query.where(AuditLog.repository_name == repository)
    candidates = db.exec(query).all()
    return _non_superseded(db, candidates)


@router.get("/derogations", dependencies=[Depends(require_module("derogations"))])
def list_derogations(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER, UserRole.DIRECTION)),
):
    """Historique complet des dérogations accordées, consultable par tous les administrateurs."""
    return db.exec(
        select(AuditLog).where(AuditLog.decision == "DEROGATION").order_by(AuditLog.id.desc())  # type: ignore[arg-type]
    ).all()


@router.get("/history/{commit_hash}")
def get_commit_history(
    commit_hash: str = Path(..., min_length=7, max_length=64, pattern=r"^[0-9a-fA-F]+$"),
    repository: Optional[str] = None,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    Décisions prises pour un commit, par dépôt si précisé (le même hash
    peut exister sur plusieurs dépôts). Un développeur ne voit que ses
    propres commits.
    """
    query = select(AuditLog).where(AuditLog.commit_hash == commit_hash).order_by(AuditLog.id.asc())  # type: ignore[arg-type]
    if repository:
        query = query.where(AuditLog.repository_name == repository)
    entries = db.exec(query).all()
    if user.role == UserRole.DEVELOPER:
        entries = [e for e in entries if e.developer_username == user.username]
    if not entries:
        raise HTTPException(status_code=404, detail="Aucun historique trouvé pour ce commit.")
    return entries


class ApprovePayload(BaseModel):
    justification: Optional[str] = None
    # Conservé pour compatibilité avec le CLI existant ; l'identité qui compte
    # est celle de l'administrateur authentifié (JWT), pas ce champ déclaratif.
    admin_username: Optional[str] = None


@router.post("/{audit_id}/approve", dependencies=[Depends(require_module("decisions"))])
async def approve_pipeline(
    audit_id: int,
    payload: ApprovePayload,
    db: Session = Depends(get_session),
    admin: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    """
    Accorde une dérogation à un pipeline bloqué ou en attente, selon la
    règle des 4 yeux : deux administrateurs/responsables sécurité DISTINCTS
    doivent valider avant que le déploiement ne se déclenche.

    N'écrit jamais dans une entrée existante (append-only) : chaque
    étape est une NOUVELLE entrée d'audit qui référence celle qu'elle
    remplace via `supersedes_audit_id` :
      1. Première validation → décision DEROGATION_PENDING, ne débloque rien.
      2. Seconde validation, par quelqu'un d'autre → décision DEROGATION,
         déclenche effectivement le déploiement. `approved_by` porte le
         premier validateur, `four_eyes_approved_by` le second.
    """
    # Un jeton API interroge le point de contrôle, il ne gouverne pas : deux
    # validations "distinctes" par une session et un jeton du même admin
    # ne sont pas quatre yeux.
    if admin.username.startswith(API_TOKEN_PREFIX_IDENTITY):
        raise HTTPException(status_code=403, detail="Une dérogation se valide avec un compte utilisateur, pas un jeton API.")

    original = db.get(AuditLog, audit_id)
    if not original:
        raise HTTPException(status_code=404, detail="Entrée d'audit introuvable.")
    if original.decision not in _ACTIONABLE_DECISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Ce pipeline n'est pas en attente de validation (décision actuelle : {original.decision}).",
        )

    already_superseded = db.exec(
        select(AuditLog).where(AuditLog.supersedes_audit_id == audit_id)
    ).first()
    if already_superseded:
        raise HTTPException(status_code=400, detail="Ce pipeline a déjà été traité par une dérogation.")

    captured_repository = original.repository_name
    captured_commit_hash = original.commit_hash
    captured_developer = original.developer_username

    # --- Étape 1/2 : première validation, ne débloque encore rien ---
    if original.decision != "DEROGATION_PENDING":
        pending_entry = AuditLog(
            developer_username=original.developer_username,
            repository_name=original.repository_name,
            commit_hash=original.commit_hash,
            ai_anomaly_score=original.ai_anomaly_score,
            ai_explanation=original.ai_explanation,
            sonarqube_vulnerabilities=original.sonarqube_vulnerabilities,
            decision="DEROGATION_PENDING",
            justification=(
                f"Première validation par {admin.username} sur la décision '{original.decision}' d'origine"
                f" (#{original.id})" + (f" : {payload.justification}" if payload.justification else "") + "."
                " Règle des 4 yeux : une seconde validation, par un autre administrateur ou"
                " responsable sécurité, est requise avant tout déploiement."
            ),
            approved_by=admin.username,
            supersedes_audit_id=original.id,
        )
        pending_entry = append_audit_log(db, pending_entry)

        pipeline = _find_pipeline(db, captured_repository, captured_commit_hash)
        if pipeline:
            pipeline.status = PipelineStatus.DEROGATION_PENDING.value
            db.add(pipeline)
            db.commit()

        return {
            "status": "pending_second_approval",
            "message": "Première validation enregistrée. Une seconde validation, par un autre administrateur ou "
            "responsable sécurité, est requise avant que le déploiement ne se déclenche (règle des 4 yeux).",
            "audit_id": pending_entry.id,
        }

    # --- Étape 2/2 : seconde validation, par une personne distincte ---
    if original.approved_by == admin.username:
        raise HTTPException(
            status_code=403,
            detail="La règle des 4 yeux exige un second validateur distinct du premier "
            f"({admin.username} a déjà effectué la première validation).",
        )

    first_approver = original.approved_by

    derogation_entry = AuditLog(
        developer_username=original.developer_username,
        repository_name=original.repository_name,
        commit_hash=original.commit_hash,
        ai_anomaly_score=original.ai_anomaly_score,
        ai_explanation=original.ai_explanation,
        sonarqube_vulnerabilities=original.sonarqube_vulnerabilities,
        decision="DEROGATION",
        justification=(
            f"Dérogation accordée : seconde validation par {admin.username}, confirmant la première validation"
            f" de {first_approver} (#{original.id})"
            + (f" : {payload.justification}" if payload.justification else "")
            + "."
        ),
        approved_by=first_approver,
        four_eyes_approved_by=admin.username,
        supersedes_audit_id=original.id,
    )
    # Capturés avant les commit() qui suivent : chaque commit expire les
    # attributs de la session, et le lambda n'est évalué que plus tard, dans
    # le thread d'arrière-plan, sur une instance devenue détachée.
    derogation_entry = append_audit_log(db, derogation_entry)

    pipeline = _find_pipeline(db, captured_repository, captured_commit_hash)
    if pipeline:
        # "DEPLOYING", pas "DEPLOYED" : le déploiement n'est encore que
        # planifié en tâche de fond ci-dessous, deployment_flow() est seul
        # à savoir s'il aboutit réellement, et posera le statut final.
        pipeline.status = PipelineStatus.DEPLOYING.value
        db.add(pipeline)
        db.commit()

    captured_pipeline_id = pipeline.id if pipeline else None

    # Module Notifications & Alertes (désactivé par défaut) : best-effort,
    # ne bloque jamais l'octroi de la dérogation elle-même si l'envoi échoue.
    try:
        await asyncio.to_thread(
            notify_derogation_granted,
            db,
            repository=captured_repository,
            commit_hash=captured_commit_hash,
            developer_username=captured_developer,
            approved_by=first_approver,
            four_eyes_approved_by=admin.username,
        )
    except Exception as e:
        logger.warning(f"Échec d'envoi de la notification de dérogation pour {captured_repository} : {e}")

    # Job de la file : la réponse n'attend pas la synchronisation Argo CD.
    defer_deployment(captured_pipeline_id, captured_repository, captured_commit_hash, derogation_entry.id)

    return {
        "status": "success",
        "message": "Seconde validation confirmée (règle des 4 yeux), dérogation accordée, déploiement déclenché.",
        "audit_id": derogation_entry.id,
    }


class DerogationRequestPayload(BaseModel):
    justification: str


@router.post("/{audit_id}/request-derogation", dependencies=[Depends(require_module("decisions"))])
def request_derogation(
    audit_id: int,
    payload: DerogationRequestPayload,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    Un développeur soumet une demande de dérogation sur son propre
    pipeline bloqué ou en attente. Ceci ne débloque rien par soi-même, ça
    place la demande, avec sa justification écrite, dans la file que les
    administrateurs consultent via /pending, en réutilisant le même
    mécanisme append-only que les dérogations elles-mêmes.
    """
    original = db.get(AuditLog, audit_id)
    if not original:
        raise HTTPException(status_code=404, detail="Entrée d'audit introuvable.")
    if original.decision not in ("WAITING_HUMAN", "BLOCKED"):
        raise HTTPException(
            status_code=400,
            detail=f"Ce pipeline n'est ni bloqué ni en attente (décision actuelle : {original.decision}).",
        )
    if user.role == UserRole.DEVELOPER and original.developer_username != user.username:
        raise HTTPException(status_code=403, detail="Vous ne pouvez demander une dérogation que sur vos propres pushs.")

    already_superseded = db.exec(select(AuditLog).where(AuditLog.supersedes_audit_id == audit_id)).first()
    if already_superseded:
        raise HTTPException(status_code=400, detail="Ce pipeline a déjà une demande ou une décision en cours.")

    request_entry = AuditLog(
        developer_username=original.developer_username,
        repository_name=original.repository_name,
        commit_hash=original.commit_hash,
        ai_anomaly_score=original.ai_anomaly_score,
        ai_explanation=original.ai_explanation,
        sonarqube_vulnerabilities=original.sonarqube_vulnerabilities,
        decision="DEROGATION_REQUESTED",
        justification=f"Dérogation demandée par {user.username} : {payload.justification}",
        supersedes_audit_id=original.id,
    )
    request_entry = append_audit_log(db, request_entry)

    return {
        "status": "success",
        "message": "Demande de dérogation enregistrée, un administrateur va l'examiner.",
        "audit_id": request_entry.id,
    }
