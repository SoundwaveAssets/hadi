"""
Politique de mot de passe, définie une seule fois : la longueur minimale
vient de Settings (ORCHESTRATOR_PASSWORD_MIN_LENGTH), lue à la validation
et non à l'import, pour que la variable ait réellement un effet.
"""
from typing import Annotated

from pydantic import AfterValidator

from app.config import get_settings


def validate_password_strength(value: str) -> str:
    minimum = get_settings().password_min_length
    if len(value) < minimum:
        raise ValueError(f"le mot de passe doit contenir au moins {minimum} caractères")
    if value.strip() != value:
        raise ValueError("le mot de passe ne doit ni commencer ni finir par une espace")
    return value


#: À utiliser dans tout schéma Pydantic qui reçoit un nouveau mot de passe.
Password = Annotated[str, AfterValidator(validate_password_strength)]
