"""
Les deux jobs de la file : analyse d'un commit, déploiement d'un commit
approuvé. `lock=<dépôt>` : jamais deux jobs du même dépôt en même temps ;
`queueing_lock` : jamais deux fois le même job en attente.

Depuis une route (boucle d'uvicorn) : defer_analysis / defer_deployment,
qui confient le dépôt à la boucle de la file. Depuis un job (déjà sur cette
boucle) : enqueue_deployment.
"""
from __future__ import annotations

import asyncio
import logging

from procrastinate import RetryStrategy
from procrastinate.exceptions import AlreadyEnqueued
from sqlmodel import Session

from app.core.database import db_manager
from app.orchestration.flows import deployment_flow, security_analysis_flow
from app.orchestration.queue import queue, worker
from app.orchestration.watchdog import sweep
from app.services.notifier import Message, deliver

logger = logging.getLogger(__name__)


@queue.task(name="hadi.analyse", queue="analyse")
async def analyse(
    pipeline_id: int | None, repository: str, commit_hash: str, author: str, ai_metadata: dict, identity_source: str | None = None
) -> str:
    return await security_analysis_flow(pipeline_id, repository, commit_hash, author, ai_metadata, identity_source)


@queue.task(name="hadi.deploiement", queue="deploiement")
async def deploy(pipeline_id: int | None, repository: str, commit_hash: str, audit_id: int | None = None) -> bool:
    return await deployment_flow(pipeline_id, repository, commit_hash, audit_id)


@queue.task(
    name="hadi.notification",
    queue="notifications",
    # Un serveur SMTP indisponible est presque toujours temporaire : on
    # réessaie sur une heure environ plutôt que de perdre l'alerte.
    retry=RetryStrategy(max_attempts=5, exponential_wait=4),
)
async def notification(recipients: list[str], subject: str, body: str) -> None:
    message = Message(recipients=recipients, subject=subject, body=body)
    with Session(db_manager.engine) as session:
        # smtplib est bloquant : jamais sur la boucle de la file.
        await asyncio.to_thread(deliver, session, message)


@queue.periodic(cron="*/10 * * * *")
@queue.task(name="hadi.chien_de_garde", queue="maintenance", pass_context=True)
async def watchdog(context, timestamp: int) -> int:
    """
    Toutes les dix minutes : les pipelines figés (worker arrêté, job perdu)
    repassent en échec au lieu d'afficher éternellement un travail en cours.
    """
    return await sweep()


async def _enqueue(deferrer, **kwargs) -> int | None:
    try:
        return await deferrer.defer_async(**kwargs)
    except AlreadyEnqueued:
        logger.info("Job déjà en attente, dépôt ignoré : %s", kwargs)
        return None


async def enqueue_deployment(pipeline_id: int | None, repository: str, commit_hash: str, audit_id: int | None) -> int | None:
    deferrer = deploy.configure(lock=repository, queueing_lock=f"deploiement:{repository}:{commit_hash}")
    return await _enqueue(deferrer, pipeline_id=pipeline_id, repository=repository, commit_hash=commit_hash, audit_id=audit_id)


async def enqueue_analysis(
    pipeline_id: int | None, repository: str, commit_hash: str, author: str, ai_metadata: dict, identity_source: str | None = None
) -> int | None:
    deferrer = analyse.configure(lock=repository, queueing_lock=f"analyse:{repository}:{commit_hash}")
    return await _enqueue(
        deferrer,
        pipeline_id=pipeline_id,
        repository=repository,
        commit_hash=commit_hash,
        author=author,
        ai_metadata=ai_metadata,
        identity_source=identity_source,
    )


def defer_analysis(
    pipeline_id: int | None, repository: str, commit_hash: str, author: str, ai_metadata: dict, identity_source: str | None = None
) -> int | None:
    return worker.submit(enqueue_analysis(pipeline_id, repository, commit_hash, author, ai_metadata, identity_source)).result(timeout=15)


def defer_deployment(pipeline_id: int | None, repository: str, commit_hash: str, audit_id: int | None = None) -> int | None:
    return worker.submit(enqueue_deployment(pipeline_id, repository, commit_hash, audit_id)).result(timeout=15)


def defer_notification(message: Message) -> int | None:
    """Depuis n'importe quel thread : une notification n'est jamais envoyée dans le fil de la requête."""
    return worker.submit(
        notification.defer_async(recipients=list(message.recipients), subject=message.subject, body=message.body)
    ).result(timeout=15)
