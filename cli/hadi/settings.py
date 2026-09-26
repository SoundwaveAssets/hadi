"""Emplacement de la configuration (platformdirs) et adresse de l'API."""
from __future__ import annotations

import json
import os
from pathlib import Path

from platformdirs import user_config_path

DEFAULT_API_URL = "http://localhost:8000/api"

CONFIG_DIR: Path = user_config_path("hadi", appauthor=False)
CONFIG_FILE = CONFIG_DIR / "config.json"


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_private(path: Path, data: dict) -> None:
    """Fichier lisible par l'utilisateur seul (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)


def api_url() -> str:
    return (os.getenv("HADI_API_URL") or read_json(CONFIG_FILE).get("api_url") or DEFAULT_API_URL).rstrip("/")


def set_api_url(url: str) -> str:
    url = url.rstrip("/")
    write_private(CONFIG_FILE, {**read_json(CONFIG_FILE), "api_url": url})
    return url
