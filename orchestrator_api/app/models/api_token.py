from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from app.models.user import UserRole


class ApiToken(SQLModel, table=True):
    """
    Compte de service : un jeton opaque et révocable, avec un rôle fixe, pour
    les scripts et intégrations.

    Seul le condensat SHA-256 est stocké ; le jeton n'est affiché qu'à la
    création. Sans `expires_at`, il reste valide jusqu'à révocation.
    """

    __tablename__ = "api_tokens"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(description="Libellé libre : à quoi sert ce jeton (ex: 'Export nocturne Direction').")
    token_hash: str = Field(index=True, unique=True)
    token_prefix: str = Field(description="8 premiers caractères du jeton, pour l'identifier sans jamais stocker le reste.")
    role: UserRole = Field(default=UserRole.DEVELOPER, description="Rôle avec lequel ce jeton agit sur l'API.")
    created_by: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_used_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    #: Date d'expiration optionnelle. None = valide jusqu'à révocation manuelle.
    #: Recommandé en production : 90 jours maximum pour les comptes de service.
    expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    is_revoked: bool = Field(default=False)
    revoked_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
