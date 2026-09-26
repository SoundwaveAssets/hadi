"""
Clé de scellement du journal d'audit et point de bascule SHA-256 -> HMAC.

La clé vit hors de la base (ORCHESTRATOR_AUDIT_KEY, sinon local_data/audit.key),
voir domain/audit_chain.py pour le pourquoi. Le fichier `audit.genesis`
fixe, lui aussi hors de la base, où s'arrête l'ancien chaînage SHA-256 et
où commence le HMAC : l'identifiant de la dernière entrée héritée et son
condensat. Sans cet ancrage, qui écrit en base pourrait effacer la bascule
et re-sceller toute la chaîne avec l'algorithme public.
"""
import json
import secrets

from app.core.secrets_store import LOCAL_DATA_DIR, load_or_create_secret

AUDIT_KEY: bytes = load_or_create_secret("ORCHESTRATOR_AUDIT_KEY", "audit.key", lambda: secrets.token_bytes(32))

_GENESIS_FILE = LOCAL_DATA_DIR / "audit.genesis"


def read_genesis() -> dict | None:
    """{"id": int, "entry_hash": str} ; None tant qu'aucune entrée HMAC n'a été écrite."""
    if not _GENESIS_FILE.exists():
        return None
    try:
        data = json.loads(_GENESIS_FILE.read_text(encoding="utf-8"))
        return {"id": int(data["id"]), "entry_hash": str(data["entry_hash"])}
    except (ValueError, KeyError, OSError):
        return None


def write_genesis(last_legacy_id: int, last_legacy_hash: str) -> dict:
    _GENESIS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {"id": last_legacy_id, "entry_hash": last_legacy_hash}
    _GENESIS_FILE.write_text(json.dumps(data), encoding="utf-8")
    return data
