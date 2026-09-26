from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class ForgeIdentity(SQLModel, table=True):
    """
    Compte de forge relié à un utilisateur Hadi. Un push dont le login
    authentifié correspond est attribué à cet utilisateur (voir
    domain/identity.py) : c'est ce qui permet à un développeur de retrouver
    ses pipelines et à la règle des quatre yeux de comparer des humains,
    pas des chaînes. Relié par un administrateur, jamais revendiqué par
    l'intéressé.
    """

    __tablename__ = "forge_identities"
    __table_args__ = (UniqueConstraint("provider", "login", name="uq_forge_identities_provider_login"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    provider: str = Field(description="gitea | github | gitlab")
    login: str
    #: Identifiant numérique côté forge, stable même si le login change.
    external_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
