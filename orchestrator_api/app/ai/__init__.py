"""
Détection d'anomalies comportementales : bibliothèque interne, pas un
service. Le modèle est entraîné et interrogé dans le process de l'API.

Répartition : `features.py` construit le vecteur, `infer.py` calcule le score
(fonction pure), `store.py` lit et écrit le profil en base, et ce module
enchaîne les trois.
"""
import asyncio
import logging

from sqlmodel import Session

from app.ai.infer import calculate_anomaly_score
from app.ai.store import ProfileStore

logger = logging.getLogger(__name__)

__all__ = ["get_anomaly_score", "get_profile_stats"]


async def get_anomaly_score(session: Session, repository: str, commit_hash: str, author: str, metadata: dict) -> dict:
    """
    Calcule un score ET une explication des facteurs déclencheurs. Ne décide
    jamais rien elle-même, transmet exclusivement un score et une
    explication au Moteur de décision (decision_engine.py), qui reste seul
    décisionnaire.

    L'entraînement IsolationForest est synchrone (scikit-learn) ; délégué à
    un thread (`asyncio.to_thread`) pour ne jamais bloquer la boucle asyncio
    de FastAPI le temps du fit. La session, elle, ne quitte pas ce thread-ci :
    le profil est lu avant, et le push enregistré après.

    Une panne remonte à l'appelant : c'est `decision_engine._collect_anomaly`
    qui décide quoi en faire. L'avaler ici en renvoyant 0.0 rendait une
    défaillance du moteur indiscernable d'un comportement mesuré comme normal.
    """
    payload = {
        "developer": author,
        "repository": repository,
        "commit_hash": commit_hash,
        **metadata,
    }
    store = ProfileStore(session)
    profile = store.get_profile(author)
    result = await asyncio.to_thread(calculate_anomaly_score, payload, profile)
    store.record_push(author, result["features"], result["changed_files"])
    return {"score": result["anomaly_score"], "explanation": "; ".join(result["explanation"])}


def get_profile_stats(session: Session) -> dict:
    """Résumé pour les pages Intégrations/Monitoring : profils appris par développeur."""
    return ProfileStore(session).stats()
