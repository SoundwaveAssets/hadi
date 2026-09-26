"""
Extraction des features comportementales à partir des métadonnées d'un push :
heure habituelle des push, volume habituel de modifications, fichiers
habituellement concernés.
"""
from typing import Any

# Ordre stable : réutilisé partout où un vecteur de features est construit ou
# expliqué, pour que l'indice d'une feature reste toujours le même.
FEATURE_NAMES = ["hour_of_day", "files_changed", "commit_count", "new_file_ratio"]


def extract_feature_vector(metadata: dict[str, Any], known_files: set[str]) -> list[float]:
    """
    Vecteur construit à partir des seules données présentes dans un payload de
    push : les forges donnent la liste des fichiers touchés, pas le nombre de
    lignes ajoutées ou supprimées.
    """
    changed_files = set(metadata.get("changed_file_paths") or [])
    new_file_ratio = 0.0
    if changed_files:
        new_files = changed_files - known_files
        new_file_ratio = len(new_files) / len(changed_files)

    return [
        float(metadata.get("hour_of_day", 12)),
        float(metadata.get("files_changed", len(changed_files))),
        float(metadata.get("commit_count", 1)),
        new_file_ratio,
    ]
