from typing import Optional

from sqlmodel import Field, SQLModel


class SystemSettings(SQLModel, table=True):
    """
    Ligne unique (id=1) suivant l'avancement du wizard d'installation.

    Vit en base plutôt que sur le disque d'une instance : c'est la source de
    vérité partagée quand l'Orchestrateur tourne en plusieurs instances
    redondantes. Le seul état qui reste local à chaque instance est
    la connexion elle-même à la base (voir core/database.py).
    """

    __tablename__ = "system_settings"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Pas d'étape "admin" : le compte admin/admin par défaut est semé
    # automatiquement (voir DatabaseManager._ensure_default_admin), à
    # changer au premier login plutôt qu'à choisir pendant l'installation.
    setup_step: str = Field(default="review", description="review | done")
    setup_locked: bool = Field(default=False)
