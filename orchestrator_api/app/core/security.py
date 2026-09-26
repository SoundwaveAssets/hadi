import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings
from app.core.secrets_store import load_or_create_secret

JWT_ALGORITHM = "HS256"

# Clé de signature JWT : voir load_or_create_secret pour la logique
# env var (recommandé, multi-instances) vs fichier local (installation simple).
_JWT_SECRET = load_or_create_secret("ORCHESTRATOR_JWT_SECRET", "jwt.key", lambda: secrets.token_bytes(32))


def hash_password(plain_password: str) -> str:
    """Hache un mot de passe avec bcrypt (sel intégré, coût par défaut)."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> str:
    if expires_minutes is None:
        expires_minutes = get_settings().jwt_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Lève jwt.PyJWTError (ExpiredSignatureError, InvalidTokenError, ...) si invalide."""
    return jwt.decode(token, _JWT_SECRET, algorithms=[JWT_ALGORITHM])



API_TOKEN_PREFIX = "orch_"


def generate_api_token() -> str:
    """
    Jeton d'accès programmatique (module Jetons API) : préfixe fixe pour le
    distinguer d'un JWT de session au premier coup d'œil dans
    `core/deps.get_current_user` (un JWT est structuré en 3 segments
    base64 séparés par des points, jamais ce préfixe).
    """
    return f"{API_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_token(token: str) -> str:
    """
    SHA-256 simple, pas bcrypt : contrairement à un mot de passe choisi par
    un humain (court, à protéger d'une attaque par dictionnaire), un jeton
    généré par `generate_api_token` a déjà une entropie élevée, un hachage
    rapide et une recherche indexée directe suffisent, pas besoin d'un
    coût de calcul artificiel.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def verify_hmac_signature(payload_body: bytes, secret_token: str, signature_header: str) -> bool:
    """
    Vérifie que la signature HMAC-SHA256 envoyée par Gitea/GitHub dans le
    header correspond bien au contenu de la requête calculé avec notre secret.

    Format attendu : "sha256=<hex>" (Gitea, GitHub) ou "<hex>" seul.
    Comparaison à temps constant pour résister aux attaques temporelles.
    """
    if not signature_header or not secret_token:
        return False

    # Gitea et GitHub envoient le header sous la forme : "sha256=MON_HASH"
    if "=" in signature_header:
        _, received_hash = signature_header.split("=", 1)
    else:
        received_hash = signature_header

    # hmac.new() est l'API correcte en Python 3 (hmac.HMAC via le constructeur).
    # On évite l'alias déprécié et on utilise directement hmac.new qui est
    # la fonction publique documentée du module hmac.
    expected_hash = hmac.new(
        secret_token.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    # Comparaison à temps constant : ne jamais utiliser == sur un condensat.
    return hmac.compare_digest(expected_hash, received_hash)