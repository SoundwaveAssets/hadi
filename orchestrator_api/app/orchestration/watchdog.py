"""
Chien de garde des pipelines figés.

`PENDING` et `DEPLOYING` sont posés AVANT que le job correspondant ne
tourne. Si le worker meurt entre les deux, ou si un job disparaît, le
pipeline reste dans cet état indéfiniment : personne n'est prévenu, rien ne
le rattrape, et le tableau de bord affiche un travail en cours qui n'existe
plus. Ce balayage périodique les fait basculer en échec, avec la raison
dans le journal d'exécution et une entrée scellée pour un déploiement.

Ce qui attend un humain (`WAITING_HUMAN`, `DEROGATION_PENDING`) n'est jamais
touché : une validation peut légitimement prendre des jours.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.config import get_settings
from app.core.database import db_manager
from app.domain.decision import DeploymentOutcome
from app.domain.pipeline_status import PipelineStatus
from app.models.audit import AuditLog, append_audit_log
from app.models.pipeline import Pipeline, append_pipeline_log

logger = logging.getLogger(__name__)

#: Statut d'arrivée selon l'étape où le pipeline s'est figé.
_FAILURE_OF = {
    PipelineStatus.PENDING.value: PipelineStatus.ANALYSIS_FAILED.value,
    PipelineStatus.DEPLOYING.value: PipelineStatus.DEPLOY_FAILED.value,
}


def sweep_stalled_pipelines(session: Session, *, now: datetime | None = None) -> list[int]:
    """
    Repasse en échec les pipelines immobiles au-delà du délai configuré
    (ORCHESTRATOR_PIPELINE_STALL_MINUTES). Renvoie les identifiants traités.
    """
    now = now or datetime.now(timezone.utc)
    limit = now - timedelta(minutes=get_settings().pipeline_stall_minutes)

    stalled = session.exec(
        select(Pipeline).where(
            Pipeline.status.in_(tuple(_FAILURE_OF)),  # type: ignore[union-attr]
            Pipeline.created_at < limit,
        )
    ).all()

    traités: list[int] = []
    for pipeline in stalled:
        previous = pipeline.status
        pipeline.status = _FAILURE_OF[previous]
        session.add(pipeline)
        reason = (
            f"Aucune progression depuis {get_settings().pipeline_stall_minutes} minutes dans l'état {previous} : "
            "le job a probablement été perdu (worker arrêté, file purgée). Relancez le pipeline."
        )
        append_pipeline_log(session, pipeline.id, f"Pipeline abandonné : {reason}")
        if previous == PipelineStatus.DEPLOYING.value:
            # Un déploiement autorisé puis jamais constaté doit laisser une
            # trace scellée : le journal ne peut pas s'arrêter sur « autorisé ».
            append_audit_log(
                session,
                AuditLog(
                    developer_username=pipeline.author,
                    developer_identity_source=pipeline.identity_source,
                    repository_name=pipeline.repository,
                    commit_hash=pipeline.commit_id,
                    decision=DeploymentOutcome.FAILED.value,
                    justification=f"Déploiement en échec : {reason}",
                ),
            )
        traités.append(pipeline.id)

    if traités:
        session.commit()
        logger.warning("Pipelines figés repassés en échec : %s", traités)
    return traités


async def sweep() -> int:
    """Point d'entrée de la tâche périodique (voir orchestration/jobs.py)."""
    from app.orchestration.queue import worker

    # Même seuil que les pipelines figés : jamais moins que la durée d'une
    # analyse légitime, sinon le balayage interromprait le travail en cours.
    repris = await worker.requeue_stalled_async(older_than_seconds=get_settings().pipeline_stall_minutes * 60)
    if repris:
        logger.info("Chien de garde : %s job(s) orphelin(s) remis en file.", repris)
    with Session(db_manager.engine) as session:
        return len(sweep_stalled_pipelines(session))
