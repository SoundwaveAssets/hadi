"""
Réglages communs. Le répertoire local (clés, ancrage HMAC, jeton
d'installation) est un dossier temporaire : les tests ne touchent jamais au
local_data/ ni à la base de l'instance de développement.
"""
import os
import tempfile

# Avant tout import de `app` : Settings est lu à l'import de app.core.secrets_store.
_LOCAL = tempfile.mkdtemp(prefix="hadi-tests-")
os.environ["ORCHESTRATOR_LOCAL_DATA_DIR"] = _LOCAL
os.environ.pop("DB_HOST", None)
os.environ["ORCHESTRATOR_SETUP_TOKEN"] = "jeton-de-test"
# Limite par IP de /login : la suite se connecte des dizaines de fois depuis
# la même adresse. On la relève ici plutôt que de la désactiver, pour que le
# décorateur reste exercé (voir test_http.py, limite de connexion).
os.environ["ORCHESTRATOR_LOGIN_RATE_LIMIT"] = "10000/minute"

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.api.routes_webhooks as webhooks
import app.core.audit_seal as seal_module
from app.core.crypto import secret_box
from app.core.database import db_manager
from app.core.security import hash_password
from app.core.state_manager import app_state_manager
from app.main import app
from app.models.module_state import ModuleState
from app.models.pipeline_config import PipelineConfig
from app.models.system import SystemSettings
from app.models.user import User, UserRole
from app.modules.registry import MODULES

PASSWORD = "un-mot-de-passe-long"
# Un seul hachage bcrypt pour toute la session : c'est lui qui faisait la durée de la suite.
HASHED = hash_password(PASSWORD)
WEBHOOK_SECRET = "secret-webhook-de-test"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(seal_module, "_GENESIS_FILE", tmp_path / "audit.genesis")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db_manager, "engine", engine)
    with Session(engine) as s:
        s.add(SystemSettings(id=1, setup_step="done", setup_locked=True))
        for m in MODULES:
            s.add(ModuleState(module_key=m.key, is_active=True))
        for name, role in (("admin", UserRole.ADMIN), ("rssi", UserRole.SECURITY_OFFICER), ("dev", UserRole.DEVELOPER)):
            s.add(User(username=name, hashed_password=HASHED, role=role))
        s.add(User(username="neuf", hashed_password=HASHED, role=UserRole.DEVELOPER, must_change_password=True))
        s.add(PipelineConfig(repository="demo", webhook_secret=secret_box.encrypt(WEBHOOK_SECRET), created_by="admin"))
        s.commit()
    app_state_manager.refresh()
    yield engine


@pytest.fixture
def client(db, monkeypatch):
    # Pas de file de travail ici : on note juste les jobs demandés.
    launched: list = []
    monkeypatch.setattr(webhooks, "defer_analysis", lambda *args, **kwargs: launched.append((*args, kwargs)))
    monkeypatch.setattr("app.api.routes_decisions.defer_analysis", lambda *args, **kwargs: launched.append((*args, kwargs)))
    monkeypatch.setattr("app.api.routes_decisions.defer_deployment", lambda *args, **kwargs: launched.append((*args, kwargs)))
    c = TestClient(app)
    c.launched = launched  # type: ignore[attr-defined]
    return c


def login(client: TestClient, username: str, password: str = PASSWORD) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def gitea_push(commit: str, message: str = "feat", delivery: str | None = None, sender: dict | None = None) -> tuple[bytes, dict]:
    """Push Gitea signé. Sans `sender`, seul le nom d'auteur Git identifie le push (cas non vérifié)."""
    payload = {
        "ref": "refs/heads/main",
        "repository": {"name": "demo"},
        "head_commit": {"id": commit, "message": message, "author": {"name": "dev"}, "timestamp": "2026-09-20T10:00:00Z", "added": ["a"], "modified": [], "removed": []},
        "commits": [{"id": commit, "added": ["a"], "modified": [], "removed": []}],
    }
    if sender:
        payload["sender"] = sender
    body = json.dumps(payload).encode()
    headers = {"X-Gitea-Signature": hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest(), "Content-Type": "application/json"}
    if delivery:
        headers["X-Gitea-Delivery"] = delivery
    return body, headers
