"""
Profil comportemental appris d'un développeur : son historique de pushs et
les fichiers qu'il a déjà touchés (voir app/ai/).

En base, et non dans un fichier de `local_data/` : plusieurs répliques de
l'API partagent alors le même profil, aucune ne réapprend dans son coin, et
redémarrer un conteneur n'efface rien. Il ne reste dans `local_data/` que ce
qui ne doit justement pas vivre dans la base qu'il protège (clé de
scellement, ancrage du journal).
"""
import json
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel


class DeveloperProfile(SQLModel, table=True):
    __tablename__ = "developer_profiles"

    #: Identité résolue du développeur (domain/identity.py), pas le nom d'auteur Git brut.
    developer: str = Field(primary_key=True)
    #: Vecteurs de features des derniers pushs, JSON (voir ai/features.py).
    history: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    #: Chemins déjà touchés, JSON, dans l'ordre d'apparition.
    known_files: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    def read(self, field: str) -> list:
        """Une valeur illisible (écriture partielle, édition manuelle) vaut profil vide, jamais une erreur d'analyse."""
        try:
            value = json.loads(getattr(self, field))
        except (TypeError, ValueError):
            return []
        return value if isinstance(value, list) else []
