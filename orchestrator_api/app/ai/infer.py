"""
Détection d'anomalies comportementales, par développeur.

IsolationForest réentraîné à chaque prédiction sur l'historique du
développeur : quelques centaines de pushs au plus, donc assez rapide, et pas
de modèle sérialisé à maintenir à jour.

Le score est relatif au profil individuel : un volume anormal pour l'un est
la routine pour l'autre.
"""
import numpy as np
from sklearn.ensemble import IsolationForest

from app.ai.features import FEATURE_NAMES, extract_feature_vector
from app.ai.store import Profile

# En dessous de ce nombre de pushs observés, il n'y a pas assez d'historique
# pour qu'IsolationForest apprenne quoi que ce soit de fiable : on renvoie un
# score neutre plutôt qu'un chiffre inventé (mode "cold start").
MIN_HISTORY_FOR_MODEL = 8

# Un facteur est jugé "explicatif" au-delà de ce nombre d'écarts-types par
# rapport à la moyenne historique du développeur.
_Z_SCORE_EXPLANATION_THRESHOLD = 2.0

_FEATURE_LABELS = {
    "hour_of_day": "l'heure du push",
    "files_changed": "le nombre de fichiers modifiés",
    "commit_count": "le nombre de commits dans le push",
    "new_file_ratio": "la proportion de fichiers jamais touchés auparavant",
}


def calculate_anomaly_score(metadata: dict, profile: Profile) -> dict:
    """
    Fonction pure : un profil entre, un score sort. Aucune session ne voyage
    dans le thread où tourne le `fit`. L'appelant reçoit le vecteur calculé et
    se charge de l'ajouter au profil.
    """
    developer = metadata.get("developer", "inconnu")
    changed_files = set(metadata.get("changed_file_paths") or [])

    features = extract_feature_vector(metadata, set(profile.known_files))
    history = profile.history
    recorded = {"features": features, "changed_files": changed_files}

    if len(history) < MIN_HISTORY_FOR_MODEL:
        return {
            **recorded,
            "anomaly_score": 0.0,
            "explanation": [
                f"Historique insuffisant pour {developer} ({len(history)}/{MIN_HISTORY_FOR_MODEL} pushs "
                "observés) : score neutre en attendant d'apprendre son profil habituel."
            ],
            "profile_status": "cold_start",
        }

    history_array = np.array(history)
    model = IsolationForest(n_estimators=100, contamination=0.1, random_state=42)
    model.fit(history_array)

    # decision_function() n'a pas d'échelle fixe. On situe donc le push dans la
    # distribution des scores de son propre historique : rang percentile, borné
    # par construction, sans constante arbitraire.
    train_scores = model.decision_function(history_array)
    raw_score = model.decision_function(np.array([features]))[0]
    normal_percentile = float((train_scores <= raw_score).mean())
    anomaly_score = float(np.clip(1.0 - normal_percentile, 0.0, 1.0))

    return {
        **recorded,
        "anomaly_score": round(anomaly_score, 2),
        "explanation": _explain(features, history_array),
        "profile_status": "established",
    }


def _explain(features: list[float], history: np.ndarray) -> list[str]:
    """
    IsolationForest ne fournit pas nativement d'attribution par feature : on
    approxime l'explication en comparant chaque feature du push courant à la
    moyenne/écart-type historique du développeur.
    """
    means = history.mean(axis=0)
    stds = history.std(axis=0)
    stds[stds == 0] = 1e-6
    z_scores = (np.array(features) - means) / stds

    reasons = []
    for name, z, value, mean in zip(FEATURE_NAMES, z_scores, features, means, strict=True):
        if abs(z) >= _Z_SCORE_EXPLANATION_THRESHOLD:
            direction = "nettement plus élevé" if z > 0 else "nettement plus bas"
            label = _FEATURE_LABELS.get(name, name)
            reasons.append(f"{label} {direction} que d'habitude ({value:.1f} vs moyenne {mean:.1f})")

    if not reasons:
        reasons.append("Comportement globalement conforme au profil habituel de ce développeur.")
    return reasons
