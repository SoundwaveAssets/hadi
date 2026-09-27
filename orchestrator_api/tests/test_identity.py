"""
Identité du pusher : le nom d'auteur Git est du texte libre, le compte
authentifié par la forge vaut identité, et un compte relié à un utilisateur
Hadi vaut identité vérifiée. Cette provenance est scellée dans l'audit.
"""
import json
from datetime import datetime, timezone

import pytest
from sqlmodel import Session, select

from app.domain.audit_chain import CURRENT_SEAL_VERSION, seal, verify_chain, verify_entry
from app.domain.identity import IdentitySource, resolve_identity
from app.models.audit import AuditLog
from app.models.forge_identity import ForgeIdentity
from app.models.pipeline import Pipeline
from app.models.user import User
from app.providers._push import parse_github_like, parse_gitlab
from app.services.identity import identify_pusher
from tests.conftest import gitea_push, login

# --- parsing des forges ---------------------------------------------------------

BASE = {"ref": "refs/heads/main", "repository": {"name": "demo"}, "head_commit": {"id": "a" * 40, "message": "m", "author": {"name": "Jean Dupont"}}, "commits": [{"id": "a" * 40}]}


def test_gitea_et_github_exposent_le_compte_authentifie():
    gitea = parse_github_like({**BASE, "sender": {"id": 7, "login": "jdupont"}, "pusher": {"id": 7, "login": "jdupont", "username": "jdupont"}})
    assert (gitea.pusher_login, gitea.pusher_id, gitea.author) == ("jdupont", "7", "Jean Dupont")

    github = parse_github_like({**BASE, "pusher": {"name": "jdupont", "email": "j@x"}, "sender": {"login": "jdupont", "id": 42}})
    assert (github.pusher_login, github.pusher_id) == ("jdupont", "42")


def test_sans_compte_authentifie_le_pusher_est_inconnu():
    event = parse_github_like(BASE)
    assert event.pusher_login is None and event.pusher_id is None and event.author == "Jean Dupont"


def test_gitlab_expose_user_username():
    payload = {"object_kind": "push", "ref": "refs/heads/main", "checkout_sha": "b" * 40, "project": {"name": "demo"}, "commits": [{"id": "b" * 40, "message": "m", "author": {"name": "Jean"}}], "user_id": 5, "user_username": "jdupont"}
    event = parse_gitlab(payload)
    assert (event.pusher_login, event.pusher_id) == ("jdupont", "5")


# --- règle pure ----------------------------------------------------------------

@pytest.mark.parametrize(
    ("mapped", "pusher", "expected_username", "expected_source"),
    [
        ("mdurand", "jdupont", "mdurand", IdentitySource.MAPPED),
        (None, "jdupont", "jdupont", IdentitySource.FORGE),
        (None, None, "Jean Dupont", IdentitySource.GIT_AUTHOR),
    ],
)
def test_resolution_du_plus_sur_au_moins_sur(mapped, pusher, expected_username, expected_source):
    identity = resolve_identity(mapped, pusher, "Jean Dupont")
    assert (identity.username, identity.source, identity.commit_author) == (expected_username, expected_source, "Jean Dupont")
    assert identity.verified is (expected_source is not IdentitySource.GIT_AUTHOR)


# --- correspondance en base -------------------------------------------------------

def test_le_login_de_forge_relie_donne_le_compte_hadi(db):
    with Session(db) as s:
        dev = s.exec(select(User).where(User.username == "dev")).first()
        s.add(ForgeIdentity(user_id=dev.id, provider="gitea", login="jdupont", external_id="7"))
        s.commit()
        by_login = identify_pusher(s, "gitea", parse_github_like({**BASE, "sender": {"id": 999, "login": "jdupont"}}))
        by_id = identify_pusher(s, "gitea", parse_github_like({**BASE, "sender": {"id": 7, "login": "renomme"}}))
        other_forge = identify_pusher(s, "github", parse_github_like({**BASE, "sender": {"id": 7, "login": "jdupont"}}))
    assert (by_login.username, by_login.source) == ("dev", IdentitySource.MAPPED)
    assert (by_id.username, by_id.source) == ("dev", IdentitySource.MAPPED)  # l'identifiant survit à un changement de login
    assert (other_forge.username, other_forge.source) == ("jdupont", IdentitySource.FORGE)  # la correspondance est par forge


# --- de bout en bout : webhook -> pipeline -> job ----------------------------------

def test_le_webhook_attribue_le_push_au_compte_relie(client, db):
    headers = login(client, "admin")
    dev_id = client.get("/api/users", headers=headers).json()[2]["id"]
    r = client.post(f"/api/users/{dev_id}/identities", json={"provider": "gitea", "login": "jdupont"}, headers=headers)
    assert r.status_code == 200, r.text

    body, sig = gitea_push("c" * 40, sender={"id": 7, "login": "jdupont"})
    assert client.post("/api/webhooks/gitea", content=body, headers=sig).status_code == 200
    with Session(db) as s:
        pipeline = s.exec(select(Pipeline).where(Pipeline.commit_id == "c" * 40)).first()
    assert (pipeline.author, pipeline.commit_author, pipeline.identity_source) == ("dev", "dev", "mapped")
    *_, kwargs = client.launched[-1]
    assert kwargs == {"identity_source": "mapped"}


def test_sans_compte_relie_le_login_de_forge_fait_foi(client, db):
    body, sig = gitea_push("d" * 40, sender={"id": 8, "login": "inconnu"})
    client.post("/api/webhooks/gitea", content=body, headers=sig)
    with Session(db) as s:
        pipeline = s.exec(select(Pipeline).where(Pipeline.commit_id == "d" * 40)).first()
    assert (pipeline.author, pipeline.identity_source) == ("inconnu", "forge")


def test_le_nom_d_auteur_seul_est_trace_comme_non_verifie(client, db):
    body, sig = gitea_push("e" * 40)
    client.post("/api/webhooks/gitea", content=body, headers=sig)
    with Session(db) as s:
        pipeline = s.exec(select(Pipeline).where(Pipeline.commit_id == "e" * 40)).first()
    assert (pipeline.author, pipeline.identity_source) == ("dev", "git-author")


# --- endpoints d'administration ---------------------------------------------------

def test_relier_une_identite_est_reserve_aux_admins_et_unique(client):
    admin = login(client, "admin")
    users = client.get("/api/users", headers=admin).json()
    dev, rssi = users[2]["id"], users[1]["id"]

    assert client.post(f"/api/users/{dev}/identities", json={"provider": "github", "login": "jdupont"}, headers=login(client, "dev")).status_code == 403
    assert client.post(f"/api/users/{dev}/identities", json={"provider": "bazar", "login": "x"}, headers=admin).status_code == 400
    assert client.post(f"/api/users/{dev}/identities", json={"provider": "github", "login": "jdupont"}, headers=admin).status_code == 200
    assert client.post(f"/api/users/{rssi}/identities", json={"provider": "github", "login": "jdupont"}, headers=admin).status_code == 409

    listed = client.get(f"/api/users/{dev}/identities", headers=admin).json()
    assert [i["login"] for i in listed] == ["jdupont"]
    assert client.delete(f"/api/users/{dev}/identities/{listed[0]['id']}", headers=admin).status_code == 200
    assert client.get(f"/api/users/{dev}/identities", headers=admin).json() == []


# --- sceau versionné ---------------------------------------------------------------

def _entry(**overrides) -> dict:
    base = {
        "id": 1, "timestamp": "2026-09-21T10:00:00+00:00", "developer_username": "dev", "repository_name": "demo",
        "commit_hash": "f" * 40, "ai_anomaly_score": 0.1, "ai_explanation": None, "sonarqube_vulnerabilities": 0,
        "decision": "AUTO_AUTH", "justification": "ok", "approved_by": None, "four_eyes_approved_by": None,
        "supersedes_audit_id": None, "developer_identity_source": "mapped",
    }
    return {**base, **overrides}


KEY = b"cle-de-test-strictement-locale-32b"


def test_une_chaine_melant_les_versions_se_verifie():
    v1 = _entry(id=1, seal_version=1)
    v1["entry_hash"] = seal(v1, None, key=KEY, version=1)
    v2 = _entry(id=2, seal_version=CURRENT_SEAL_VERSION)
    v2["entry_hash"] = seal(v2, v1["entry_hash"], key=KEY)
    assert verify_chain([v1, v2], key=KEY) == (True, None)


def test_la_provenance_est_scellee_en_v2_pas_en_v1():
    v2 = _entry(seal_version=CURRENT_SEAL_VERSION)
    v2["entry_hash"] = seal(v2, None, key=KEY)
    v2["developer_identity_source"] = "git-author"
    assert not verify_entry(v2, None, key=KEY)

    v1 = _entry(seal_version=1)
    v1["entry_hash"] = seal(v1, None, key=KEY, version=1)
    v1["developer_identity_source"] = "git-author"  # hors périmètre de la v1 : ne casse pas les anciennes entrées
    assert verify_entry(v1, None, key=KEY)


def test_changer_la_version_d_une_entree_la_fait_echouer():
    v2 = _entry(seal_version=CURRENT_SEAL_VERSION)
    v2["entry_hash"] = seal(v2, None, key=KEY)
    v2["seal_version"] = 1
    assert not verify_entry(v2, None, key=KEY)


def test_les_entrees_du_modele_portent_la_version_courante(db):
    from app.models.audit import append_audit_log, verify_chain_integrity

    with Session(db) as s:
        entry = append_audit_log(s, AuditLog(developer_username="dev", developer_identity_source="forge", repository_name="demo", commit_hash="0" * 40, decision="AUTO_AUTH", justification="ok", timestamp=datetime.now(timezone.utc)))
        assert entry.seal_version == CURRENT_SEAL_VERSION
        assert verify_chain_integrity(s) == (True, None)
        assert json.loads(json.dumps(entry.developer_identity_source)) == "forge"
