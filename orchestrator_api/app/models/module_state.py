from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class ModuleState(SQLModel, table=True):
    """
    Table de bascule (activé/désactivé) pour chaque module du registre
    (voir app/modules/registry.py). Une ligne par module, seedée
    automatiquement au démarrage de l'instance pour toute clé nouvelle
    (voir ensure_module_states dans core/database.py), jamais créée à la
    main : le registre en code reste la seule source de vérité sur QUELS
    modules existent, cette table ne retient que leur état ON/OFF.
    """

    __tablename__ = "module_states"

    module_key: str = Field(primary_key=True)
    is_active: bool = Field(default=True)
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_by: Optional[str] = Field(default=None)
