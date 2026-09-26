"""
Jeton d'installation à usage unique. Tant que l'assistant n'est pas
verrouillé, les routes /api/setup/* l'exigent en en-tête X-Setup-Token :
sans lui, le premier venu sur le réseau pointe l'instance vers sa propre base
et se fabrique un administrateur. Il vient de ORCHESTRATOR_SETUP_TOKEN, sinon
il est généré au premier démarrage, conservé dans local_data/setup.token et
affiché dans les journaux, comme initialAdminPassword chez Jenkins.
"""
import hmac
import logging
import secrets

from app.config import get_settings
from app.core.secrets_store import LOCAL_DATA_DIR

logger = logging.getLogger(__name__)

_TOKEN_FILE = LOCAL_DATA_DIR / "setup.token"


def current_token() -> str:
    env = get_settings().setup_token
    if env:
        return env
    if _TOKEN_FILE.exists():
        return _TOKEN_FILE.read_text(encoding="utf-8").strip()
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    _TOKEN_FILE.write_text(token, encoding="utf-8")
    return token


def check(candidate: str | None) -> bool:
    return bool(candidate) and hmac.compare_digest(candidate.strip(), current_token())


def announce() -> None:
    logger.warning(
        "Installation non verrouillée. Jeton d'installation à saisir dans l'assistant : %s",
        current_token(),
    )


def discard() -> None:
    if _TOKEN_FILE.exists():
        _TOKEN_FILE.unlink()
