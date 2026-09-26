"""
Lecture et mise à jour des profils comportementaux (models/developer_profile.py).

Seule couche qui connaît la persistance : `infer.py` ne reçoit qu'un profil
déjà chargé et ne sait pas d'où il vient.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models.developer_profile import DeveloperProfile

#: Fenêtre glissante : le profil suit le développeur d'aujourd'hui, pas celui d'il y a deux ans.
MAX_HISTORY_PER_DEVELOPER = 200
MAX_KNOWN_FILES_PER_DEVELOPER = 500


@dataclass
class Profile:
    history: list[list[float]] = field(default_factory=list)
    known_files: list[str] = field(default_factory=list)


class ProfileStore:
    """Une instance par session : les appelants en créent une, ils ne la partagent pas."""

    def __init__(self, session: Session):
        self.session = session

    def get_profile(self, developer: str) -> Profile:
        row = self.session.get(DeveloperProfile, developer)
        if row is None:
            return Profile()
        return Profile(history=row.read("history"), known_files=row.read("known_files"))

    def record_push(self, developer: str, features: list[float], changed_files: set[str]) -> None:
        """
        Ajoute un push au profil. La ligne est verrouillée le temps de la
        transaction (PostgreSQL) : deux workers qui traitent un push du même
        développeur en parallèle s'ajoutent l'un après l'autre au lieu de
        s'écraser. SQLite n'a qu'un écrivain, la clause est sans effet.
        """
        row = self.session.exec(
            select(DeveloperProfile).where(DeveloperProfile.developer == developer).with_for_update()
        ).first()
        if row is None:
            row = DeveloperProfile(developer=developer)

        history = [*row.read("history"), features][-MAX_HISTORY_PER_DEVELOPER:]
        # Ordre d'apparition conservé : au-delà du plafond, ce sont les fichiers
        # les plus anciens qui sortent, pas les premiers par ordre alphabétique.
        known = dict.fromkeys(row.read("known_files"))
        known.update(dict.fromkeys(sorted(changed_files - known.keys())))

        row.history = json.dumps(history)
        row.known_files = json.dumps(list(known)[-MAX_KNOWN_FILES_PER_DEVELOPER:])
        row.updated_at = datetime.now(timezone.utc)
        self.session.add(row)
        self.session.commit()

    def stats(self) -> dict:
        """Résumé pour les pages Intégrations/Monitoring : combien de profils ont été appris."""
        rows = self.session.exec(select(DeveloperProfile)).all()
        return {
            "developer_count": len(rows),
            "total_pushs_observed": sum(len(r.read("history")) for r in rows),
        }
