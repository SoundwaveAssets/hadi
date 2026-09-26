import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.core.crypto import secret_box
from app.core.database import get_session
from app.core.ratelimit import limiter
from app.domain.pipeline_status import PipelineStatus
from app.models.audit import AuditLog, append_audit_log
from app.models.pipeline import Pipeline, start_pipeline_run
from app.models.webhook_delivery import WebhookDelivery
from app.orchestration.jobs import defer_analysis
from app.providers import PROVIDERS, PushEvent
from app.services.identity import identify_pusher
from app.services.pipeline_config import get_pipeline_config

logger = logging.getLogger(__name__)
router = APIRouter()

# 1 Mio : un push GitHub/GitLab avec quelques centaines de fichiers tient en dessous.
MAX_BODY_BYTES = 1024 * 1024
# Au-delà, un identifiant de livraison est oublié : les forges ne rejouent pas plus vieux.
DELIVERY_RETENTION = timedelta(days=7)
# Un commit arrivé jusqu'au déploiement ne repart pas en analyse sur une simple
# relivraison : seule une action explicite (retrigger) le fait.
#: Un push sur un commit déjà déployé (ou en cours de déploiement) ne
#: relance rien : il faut le demander explicitement.
_SETTLED_STATUSES = {PipelineStatus.DEPLOYED.value, PipelineStatus.DEPLOYING.value}


def _acknowledge(db: Session, delivery_id: str | None, provider: str, repository: str) -> None:
    """Marque la livraison comme traitée et purge les acquittements périmés."""
    if not delivery_id:
        return
    db.add(WebhookDelivery(delivery_id=delivery_id[:128], provider=provider, repository=repository))
    db.exec(  # type: ignore[call-overload]
        WebhookDelivery.__table__.delete().where(WebhookDelivery.received_at < datetime.now(timezone.utc) - DELIVERY_RETENTION)
    )
    db.commit()


def _extract_ai_metadata(event: PushEvent) -> dict:
    """
    Métadonnées comportementales tirées du push : heure, volume de
    modifications, fichiers touchés. Rien de simulé.
    """
    files_changed: set[str] = set()
    for commit in event.commits:
        files_changed.update(commit["added"])
        files_changed.update(commit["removed"])
        files_changed.update(commit["modified"])

    hour_of_day = datetime.now(timezone.utc).hour
    if event.head_timestamp:
        try:
            hour_of_day = datetime.fromisoformat(event.head_timestamp.replace("Z", "+00:00")).hour
        except ValueError:
            pass

    return {
        "branch": event.branch,
        "commit_count": len(event.commits),
        "files_changed": len(files_changed),
        "changed_file_paths": sorted(files_changed),
        "hour_of_day": hour_of_day,
    }


@router.post("/{provider}")
@limiter.limit("60/minute")
async def receive_webhook(provider: str, request: Request, db: Session = Depends(get_session)):
    """
    Une URL par forge (/api/webhooks/gitea, /github, /gitlab) : le format
    du payload et la signature diffèrent, le reste est commun. Le dépôt
    doit être enregistré pour CETTE forge, sinon on vérifierait sa
    signature avec le mauvais schéma.
    """
    forge = PROVIDERS.get(provider)
    if forge is None:
        raise HTTPException(status_code=404, detail="Forge inconnue.")

    # Corps brut lu AVANT tout parsing : la signature porte sur les octets
    # exacts envoyés, pas sur une reconstruction du payload. Plafonné : un
    # push réel tient largement en dessous, et cette route est publique.
    raw_body = await request.body()
    if len(raw_body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Corps de requête trop volumineux.")
    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Corps de requête invalide (JSON attendu).") from e

    repo_name = forge.repository_name(payload) or "inconnu"

    # Le secret dépend du dépôt : il faut l'identifier avant de pouvoir
    # vérifier la signature. Pas d'entrée d'audit à ce stade : la requête
    # n'est pas authentifiée, et le journal chaîné n'est pas un dépotoir.
    pipeline_config = get_pipeline_config(db, repo_name)
    if not pipeline_config or not pipeline_config.is_active:
        logger.warning(f"Webhook {provider} : dépôt non enregistré ou désactivé ({repo_name[:80]!r}), push ignoré.")
        raise HTTPException(status_code=403, detail="Dépôt non enregistré ou désactivé.")

    expected = pipeline_config.vcs_provider or "gitea"
    if expected != provider:
        raise HTTPException(status_code=403, detail=f"Le dépôt '{repo_name}' est enregistré pour {expected}, pas pour {provider}.")

    webhook_secret = secret_box.decrypt(pipeline_config.webhook_secret)
    if not forge.verify_signature(raw_body, request.headers, webhook_secret):
        append_audit_log(
            db,
            AuditLog(
                developer_username="inconnu",
                repository_name=repo_name,
                commit_hash="inconnu",
                decision="REJECTED_INVALID_SIGNATURE",
                justification=f"Signature du Webhook invalide ou absente pour le pipeline '{repo_name}' : requête rejetée.",
            ),
        )
        raise HTTPException(status_code=401, detail="Signature du Webhook invalide.")

    # Garde anti-rejeu : on REGARDE ici, on n'acquitte qu'une fois le job
    # réellement confié à la file (voir plus bas). Acquitter avant, c'était
    # perdre le push pour de bon si le dépôt du job échouait : la forge
    # relivrait, Hadi répondrait « déjà traitée », et le pipeline resterait
    # figé en PENDING sans que personne ne l'apprenne.
    delivery_id = forge.delivery_id(request.headers)
    if delivery_id and db.get(WebhookDelivery, delivery_id):
        return {"message": "Livraison déjà traitée, événement ignoré.", "analysis_triggered": False}

    event = forge.parse_push(payload)
    if event is None:
        return {"message": "Événement sans commit exploitable (ping, tag, suppression de branche) : ignoré.", "analysis_triggered": False}

    # Le commit de déploiement (deployment_flow écrit le SHA dans le
    # manifeste, sur ce même dépôt) revient ici par le Webhook : sans ce
    # filtre, chaque déploiement relancerait une analyse, qui déploierait,
    # qui relancerait... Convention [skip ci], la même que les forges.
    if "[skip ci]" in event.commit_message.lower():
        return {"message": "Commit marqué [skip ci], événement ignoré.", "analysis_triggered": False}

    # Un même commit peut légitimement revenir : "Tester l'envoi" renvoie
    # toujours le même commit factice, et un vrai push peut être re-livré.
    # Un commit déjà connu pour ce dépôt relance simplement l'analyse.
    # Qui pousse ? Le compte authentifié par la forge, relié si possible à un
    # compte Hadi ; le nom d'auteur Git n'est qu'un repli, tracé comme tel.
    identity = identify_pusher(db, provider, event)

    pipeline = db.exec(
        select(Pipeline).where(Pipeline.repository == repo_name, Pipeline.commit_id == event.commit_id)
    ).first()
    if pipeline and pipeline.status in _SETTLED_STATUSES:
        return {"message": f"Commit déjà {pipeline.status.lower()} : relancez explicitement si nécessaire.", "pipeline_id": pipeline.id, "analysis_triggered": False}
    if pipeline:
        pipeline.branch = event.branch
        pipeline.commit_message = event.commit_message
        pipeline.author = identity.username
        pipeline.commit_author = identity.commit_author
        pipeline.identity_source = identity.source.value
        start_pipeline_run(db, pipeline, "push reçu")
    else:
        pipeline = Pipeline(
            repository=repo_name,
            branch=event.branch,
            commit_id=event.commit_id,
            commit_message=event.commit_message,
            author=identity.username,
            commit_author=identity.commit_author,
            identity_source=identity.source.value,
            status=PipelineStatus.PENDING.value,
        )
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)

    # L'analyse est un job de la file : le Webhook répond tout de suite, la
    # forge n'attend pas les minutes du build.
    pipeline_id = pipeline.id
    try:
        defer_analysis(pipeline_id, repo_name, event.commit_id, identity.username, _extract_ai_metadata(event), identity_source=identity.source.value)
    except Exception as error:
        logger.error("Dépôt du job d'analyse impossible pour %s/%s : %s", repo_name, event.commit_id[:7], error)
        # 503 et aucune livraison acquittée : la forge relivrera, et cette
        # fois le push sera traité.
        raise HTTPException(
            status_code=503,
            detail="File de travail indisponible : l'analyse n'a pas pu être lancée, la livraison sera rejouée.",
        ) from error

    _acknowledge(db, delivery_id, provider, repo_name)
    return {"status": "success", "message": "Webhook traité et pipeline initialisé", "pipeline_id": pipeline_id, "analysis_triggered": True}
