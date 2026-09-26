"""
Session locale. Le jeton va dans le magasin d'identifiants de l'OS (keyring :
Credential Manager, Trousseau, Secret Service) ; sans magasin disponible
(serveur sans bureau, conteneur), repli sur un fichier 0600. Le reste de la
session (compte, rôle) n'est pas secret et reste dans un fichier.
"""
from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError

from hadi.settings import CONFIG_DIR, api_url, read_json, write_private

SESSION_FILE = CONFIG_DIR / "session.json"
_SERVICE = "hadi"


def save(data: dict) -> None:
    token = data.get("access_token")
    public = {k: v for k, v in data.items() if k != "access_token"}
    # Relire après écriture : un magasin absent lève, mais un magasin « nul »
    # accepte en silence et perdrait le jeton.
    try:
        keyring.set_password(_SERVICE, api_url(), token)
        stored = keyring.get_password(_SERVICE, api_url()) == token
    except KeyringError:
        stored = False
    if not stored:
        public["access_token"] = token  # pas de magasin : le fichier 0600 fait office
    write_private(SESSION_FILE, public)


def token() -> str | None:
    """Priorité à HADI_TOKEN (scripts, CI), puis le magasin de l'OS, puis le fichier de repli."""
    if os.getenv("HADI_TOKEN"):
        return os.environ["HADI_TOKEN"]
    try:
        stored = keyring.get_password(_SERVICE, api_url())
    except KeyringError:
        stored = None
    return stored or read_json(SESSION_FILE).get("access_token")


def clear() -> None:
    try:
        keyring.delete_password(_SERVICE, api_url())
    except KeyringError:
        pass
    SESSION_FILE.unlink(missing_ok=True)
