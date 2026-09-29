"""
CLI hadi : session (magasin de l'OS ou fichier de repli), configuration,
rendu des commandes et codes de sortie. L'API est remplacée par des réponses
en mémoire : ces tests ne parlent à aucun serveur.
"""
from __future__ import annotations

import json
import os
import stat

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.backends.null import Keyring as NullKeyring
from typer.testing import CliRunner

from hadi import __version__, client, session, settings
from hadi.app import app

runner = CliRunner()


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(session, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.delenv("HADI_TOKEN", raising=False)
    monkeypatch.delenv("HADI_API_URL", raising=False)
    yield tmp_path


@pytest.fixture
def memory_keyring(monkeypatch):
    backend = MemoryKeyring()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(keyring, "set_password", backend.set_password)
    monkeypatch.setattr(keyring, "get_password", backend.get_password)
    monkeypatch.setattr(keyring, "delete_password", backend.delete_password)
    return backend


@pytest.fixture
def no_keyring(monkeypatch):
    null = NullKeyring()
    monkeypatch.setattr(keyring, "set_password", null.set_password)
    monkeypatch.setattr(keyring, "get_password", null.get_password)
    monkeypatch.setattr(keyring, "delete_password", null.delete_password)


# --- session -----------------------------------------------------------------

def test_le_jeton_va_dans_le_magasin_de_l_os(memory_keyring, isolated_home):
    session.save({"access_token": "abc", "username": "dev", "role": "developer"})
    assert memory_keyring.store == {("hadi", settings.api_url()): "abc"}
    assert "access_token" not in json.loads((isolated_home / "session.json").read_text())
    assert session.token() == "abc"
    session.clear()
    assert session.token() is None and not (isolated_home / "session.json").exists()


def test_sans_magasin_le_fichier_prive_fait_office(no_keyring, isolated_home):
    session.save({"access_token": "abc", "username": "dev"})
    path = isolated_home / "session.json"
    assert json.loads(path.read_text())["access_token"] == "abc"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert session.token() == "abc"


def test_hadi_token_prime_sur_la_session(memory_keyring, monkeypatch):
    session.save({"access_token": "stocke"})
    monkeypatch.setenv("HADI_TOKEN", "env")
    assert session.token() == "env"


# --- configuration -------------------------------------------------------------

def test_api_url_par_defaut_puis_configuree_puis_env(monkeypatch):
    assert settings.api_url() == settings.DEFAULT_API_URL
    result = runner.invoke(app, ["config", "--api-url", "http://hadi.exemple.org/api/"])
    assert result.exit_code == 0 and settings.api_url() == "http://hadi.exemple.org/api"
    monkeypatch.setenv("HADI_API_URL", "http://autre/api")
    assert settings.api_url() == "http://autre/api"


# --- commandes ------------------------------------------------------------------

@pytest.fixture
def fake_api(monkeypatch):
    """Remplace client.get/client.post par un dictionnaire chemin -> réponse."""
    responses: dict[str, object] = {}
    calls: list[tuple[str, str, dict]] = []

    def get(path, **kwargs):
        calls.append(("GET", path, kwargs))
        return responses[path]

    def post(path, **kwargs):
        calls.append(("POST", path, kwargs))
        return responses[path]

    monkeypatch.setattr(client, "get", get)
    monkeypatch.setattr(client, "post", post)
    # Les commandes passent par hadi.commands.* qui ont importé `client` en module : même objet, patch visible.
    responses["__calls__"] = calls
    return responses


def test_version_et_aide():
    assert f"hadi {__version__}" in runner.invoke(app, ["--version"]).output
    output = runner.invoke(app, ["--help"]).output
    for command in ("login", "pipelines", "watch", "approve", "audit-verify", "gate", "shell"):
        assert command in output


def test_pipelines_rendu_table_et_json(fake_api):
    fake_api["/decisions/pipelines"] = {"total": 1, "items": [{"id": 7, "repository": "demo", "branch": "main", "commit_id": "abcdef1234", "author": "dev", "status": "DEPLOYED"}]}
    human = runner.invoke(app, ["pipelines", "--limit", "5"])
    assert human.exit_code == 0 and "demo" in human.output and "abcdef12" in human.output
    assert fake_api["__calls__"][-1][2]["params"] == {"limit": 5}

    machine = runner.invoke(app, ["--json", "pipelines"])
    assert json.loads(machine.output)[0]["id"] == 7


def test_watch_s_arrete_sur_un_etat_definitif(fake_api, monkeypatch):
    states = iter(["PENDING", "DEPLOYING", "DEPLOYED"])
    monkeypatch.setattr(client, "get", lambda path, **kw: {"id": 3, "repository": "demo", "commit_id": "abcdef1234", "status": next(states)})
    monkeypatch.setattr("hadi.commands.pipelines.time.sleep", lambda s: None)
    result = runner.invoke(app, ["watch", "3", "--interval", "0"])
    assert result.exit_code == 0
    assert result.output.count("demo") == 3


def test_watch_code_de_sortie_1_si_bloque(fake_api, monkeypatch):
    monkeypatch.setattr(client, "get", lambda path, **kw: {"id": 3, "repository": "demo", "commit_id": "abcdef1234", "status": "BLOCKED"})
    result = runner.invoke(app, ["watch", "3"])
    assert result.exit_code == 1 and "hadi retrigger 3" in result.output


def test_approve_transmet_la_justification(fake_api):
    fake_api["/decisions/42/approve"] = {"status": "pending_second_approval", "message": "Première validation enregistrée."}
    result = runner.invoke(app, ["approve", "42", "-j", "hotfix validé"])
    assert result.exit_code == 0 and "Première validation" in result.output
    assert fake_api["__calls__"][-1] == ("POST", "/decisions/42/approve", {"json": {"justification": "hotfix validé"}})


def test_audit_verify_echoue_si_l_une_des_chaines_est_rompue(fake_api):
    fake_api["/audit/verify"] = {"status": "intact", "message": "ok"}
    fake_api["/audit/admin-events/verify"] = {"status": "corrupted", "message": "Rupture à l'événement 12."}
    result = runner.invoke(app, ["audit-verify"])
    assert result.exit_code == 1 and "décisions intact" in result.output and "Rupture" in result.output


def test_admin_events_filtre_et_rend(fake_api):
    fake_api["/audit/admin-events"] = {"total": 1, "entries": [{"id": 9, "timestamp": "2026-09-21T10:00:00+00:00", "actor": "admin", "action": "user.create", "target_type": "user", "target_id": "5", "target_label": "bob", "ip": "10.0.0.1"}]}
    result = runner.invoke(app, ["admin-events", "--action", "user.", "-n", "10"])
    assert result.exit_code == 0 and "user.create" in result.output and "bob" in result.output
    assert fake_api["__calls__"][-1][2]["params"] == {"limit": 10, "action": "user."}


def test_sans_session_les_commandes_refusent(no_keyring):
    result = runner.invoke(app, ["whoami"])
    assert result.exit_code == 1 and "hadi login" in result.output


def test_watch_s_arrete_sur_une_attente_humaine(fake_api, monkeypatch):
    """Un job CI n'a pas à immobiliser un agent pendant qu'un administrateur réfléchit."""
    monkeypatch.setattr(client, "get", lambda path, **kw: {"id": 3, "repository": "demo", "commit_id": "abcdef1234", "status": "WAITING_HUMAN"})
    result = runner.invoke(app, ["watch", "3"])
    assert result.exit_code == 1 and "décision humaine" in result.output


def test_watch_abandonne_au_dela_du_delai(fake_api, monkeypatch):
    monkeypatch.setattr(client, "get", lambda path, **kw: {"id": 3, "repository": "demo", "commit_id": "abcdef1234", "status": "PENDING"})
    monkeypatch.setattr("hadi.commands.pipelines.time.sleep", lambda s: None)
    result = runner.invoke(app, ["watch", "3", "--timeout", "0" if False else "1", "--interval", "0"])
    assert result.exit_code == 2 and "abandon du suivi" in result.output


def test_un_hash_de_commit_colle_seul_devient_un_historique():
    """Cas vécu : coller un hash dans le shell répondait « No such command »."""
    from hadi.app import _looks_like_commit

    assert _looks_like_commit("c67830a6c717a12e052cebf99de40dbdc") is True
    # Une empreinte SHA-256 (64 caractères) n'est pas un commit : elle ne doit
    # pas partir chercher un historique qui n'existe pas.
    assert _looks_like_commit("c67830a6c717a12e052cebf99de40dbdc7ac2a84e6b96f5828b75755e47e0935") is False
    assert _looks_like_commit("pipelines") is False
