from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class UserRole(str, Enum):
    """Rôles applicatifs disponibles."""

    DEVELOPER = "developer"
    ADMIN = "admin"
    SECURITY_OFFICER = "security_officer"
    DIRECTION = "direction"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: Optional[str] = Field(default=None)
    hashed_password: str
    role: UserRole = Field(default=UserRole.DEVELOPER)
    is_active: bool = Field(default=True)
    # Vrai pour le compte admin/admin généré automatiquement à l'installation
    # (façon SonarQube) : le Dashboard bloque toute autre action tant que ce
    # mot de passe par défaut n'a pas été changé.
    must_change_password: bool = Field(default=False)

    # Protection anti-brute-force sur /login (voir routes_auth.py) : compteur
    # remis à zéro à chaque connexion réussie, verrouillage temporaire du
    # compte au-delà du seuil. En base plutôt qu'en mémoire du process, pour
    # rester valable même si l'Orchestrateur tourne en plusieurs instances.
    failed_login_attempts: int = Field(default=0)
    locked_until: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
