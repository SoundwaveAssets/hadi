import logging
import os
from collections.abc import Callable
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

# Chemin absolu (voir config.py) : relatif, lancer uvicorn d'ailleurs
# régénérait des clés et rendait les secrets en base indéchiffrables.
LOCAL_DATA_DIR: Path = get_settings().local_data_dir


def load_or_create_secret(env_var: str, filename: str, generator: Callable[[], bytes]) -> bytes:
    """
    Secret persistant : la variable d'environnement d'abord (seule façon de
    partager la valeur entre plusieurs instances), sinon un fichier généré
    une fois dans local_data/.
    """
    env_value = os.getenv(env_var)
    if env_value:
        return env_value.encode("utf-8")

    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCAL_DATA_DIR / filename
    if path.exists():
        return path.read_bytes()

    value = generator()
    # 0600 : la clé maître et la clé JWT ne regardent que l'utilisateur du service.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(value)
    logger.warning(
        f"{env_var} non fournie : un secret a été généré localement dans {path}. "
        f"Pour un déploiement multi-instances, exportez {env_var} avec la même valeur "
        "sur toutes les instances plutôt que de compter sur ce fichier."
    )
    return value
