from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class CompliancePolicyType(str, Enum):
    DEPLOYMENT_WINDOW = "deployment_window"
    REINFORCED_REPOSITORY = "reinforced_repository"


class CompliancePolicy(SQLModel, table=True):
    """
    Règle appliquée par services/compliance.py en plus du moteur de décision,
    jamais à sa place : elle peut durcir un verdict (AUTO_AUTH -> WAITING_HUMAN),
    jamais l'assouplir.

    Chaque type n'utilise qu'un sous-ensemble des champs :
    - DEPLOYMENT_WINDOW : hors de la fenêtre (jours et heures UTC), un
      AUTO_AUTH redescend en WAITING_HUMAN.
    - REINFORCED_REPOSITORY : tout push sur un dépôt dont le nom contient
      `repository_pattern` passe par un humain.
    """

    __tablename__ = "compliance_policies"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    policy_type: CompliancePolicyType
    is_active: bool = Field(default=True)
    created_by: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # --- DEPLOYMENT_WINDOW ---
    allowed_days: Optional[str] = Field(
        default=None, description="Jours autorisés, ex. '0,1,2,3,4' (0=lundi..6=dimanche). Vide = tous les jours."
    )
    allowed_start_hour: Optional[int] = Field(default=None, description="Heure de début autorisée, 0-23 UTC.")
    allowed_end_hour: Optional[int] = Field(default=None, description="Heure de fin autorisée, exclue, 0-23 UTC. Inférieure au début, la fenêtre passe minuit.")
    repository_scope: Optional[str] = Field(
        default=None,
        description="Nom exact d'un pipeline (dépôt) : la fenêtre ne s'applique qu'à lui. Vide = tous les pipelines.",
    )

    # --- REINFORCED_REPOSITORY ---
    repository_pattern: Optional[str] = Field(default=None, description="Sous-chaîne recherchée dans le nom du dépôt.")
