from datetime import datetime, timezone

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class WebhookDelivery(SQLModel, table=True):
    """
    Identifiants de livraison déjà traités (X-Gitea-Delivery, X-GitHub-Delivery,
    X-Gitlab-Event-UUID). Une livraison rejouée, même signée, ne relance rien :
    sans ça, un payload capturé remettait un pipeline déployé en PENDING.
    Purgée au fil de l'eau (voir routes_webhooks.py).
    """

    __tablename__ = "webhook_deliveries"

    delivery_id: str = Field(primary_key=True, max_length=128)
    provider: str
    repository: str
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
