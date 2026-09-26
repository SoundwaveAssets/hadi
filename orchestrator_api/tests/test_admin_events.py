"""
Journal des actions d'administration : chaque route sensible laisse une
trace scellée, jamais un secret ; la chaîne se vérifie séparément de celle
des décisions.
"""
import json

import pytest
from sqlalchemy import text
from sqlmodel import Session

import app.api.routes_pipeline_configs as pipeline_configs
from app.domain.audit_chain import ADMIN_SEAL, DECISION_SEAL, seal, verify_chain
from app.models.admin_event import verify_admin_chain
from app.services import admin_audit
from tests.conftest import PASSWORD, login


def events(client, headers, **params) -> list[dict]:
    r = client.get("/api/audit/admin-events", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["entries"]


def last(client, headers, action: str) -> dict:
    found = events(client, headers, action=action)
    assert found, f"aucun événement {action}"
    return found[0]


# --- helpers du service -----------------------------------------------------------

def test_les_secrets_sont_masques_jamais_absents():
    masked = admin_audit.redact({"jenkins_url": "http://j", "jenkins_token": "abc", "smtp_password": "", "webhook_secret": "s"})
    assert masked == {"jenkins_url": "http://j", "jenkins_token": "***", "smtp_password": None, "webhook_secret": "***"}


def test_le_diff_ne_garde_que_les_changements_et_tout_secret_envoye():
    before, after = admin_audit.diff({"role": "developer", "is_active": True, "argocd_token": "old"}, {"role": "admin", "is_active": True, "argocd_token": "new"})
    assert before == {"role": "developer", "argocd_token": "old"}
    assert after == {"role": "admin", "argocd_token": "new"}


# --- comptes ----------------------------------------------------------------------

def test_creer_un_compte_laisse_une_trace_sans_mot_de_passe(client):
    headers = login(client, "admin")
    r = client.post("/api/users", json={"username": "nouveau", "password": PASSWORD, "role": "developer"}, headers=headers)
    assert r.status_code == 200
    event = last(client, headers, "user.create")
    assert event["actor"] == "admin" and event["actor_role"] == "admin"
    assert event["target_type"] == "user" and event["target_label"] == "nouveau" and event["target_id"] == str(r.json()["id"])
    assert json.loads(event["after"]) == {"username": "nouveau", "email": None, "role": "developer", "is_active": True}
    assert PASSWORD not in json.dumps(event)


def test_changer_un_role_journalise_avant_et_apres(client):
    headers = login(client, "admin")
    dev_id = client.get("/api/users", headers=headers).json()[2]["id"]
    assert client.patch(f"/api/users/{dev_id}", json={"role": "security_officer"}, headers=headers).status_code == 200
    event = last(client, headers, "user.update")
    assert json.loads(event["before"]) == {"role": "developer"} and json.loads(event["after"]) == {"role": "security_officer"}


def test_relier_et_retirer_une_identite_de_forge(client):
    headers = login(client, "admin")
    dev_id = client.get("/api/users", headers=headers).json()[2]["id"]
    r = client.post(f"/api/users/{dev_id}/identities", json={"provider": "github", "login": "octocat"}, headers=headers)
    assert r.status_code == 200
    assert json.loads(last(client, headers, "user.identity.add")["after"]) == {"provider": "github", "login": "octocat", "external_id": None}
    assert client.delete(f"/api/users/{dev_id}/identities/{r.json()['id']}", headers=headers).status_code == 200
    removed = last(client, headers, "user.identity.remove")
    assert removed["target_label"] == "dev" and json.loads(removed["before"])["login"] == "octocat"


# --- connexions -------------------------------------------------------------------

def test_connexion_echec_et_verrouillage_journalises_pour_les_comptes_existants(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "dev", "password": "faux"})
    client.post("/api/auth/login", json={"username": "inexistant", "password": "faux"})
    headers = login(client, "admin")
    failed = events(client, headers, action="auth.login_failed")
    assert len(failed) == 4 and all(e["actor"] == "dev" and e["ip"] for e in failed)
    assert len(events(client, headers, action="auth.lockout")) == 1
    assert not events(client, headers, actor="inexistant")
    assert last(client, headers, "auth.login")["actor"] == "admin"


def test_changement_de_mot_de_passe_journalise(client):
    headers = login(client, "neuf")
    r = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "encore-plus-long-que-douze"}, headers=headers)
    assert r.status_code == 200
    admin = login(client, "admin")
    event = last(client, admin, "auth.password_change")
    assert event["actor"] == "neuf" and event["before"] is None and event["after"] is None


# --- intégrations, modules, politiques, pipelines --------------------------------------

def test_enregistrer_un_jeton_d_outil_ne_le_journalise_jamais_en_clair(client):
    headers = login(client, "rssi")
    assert client.post("/api/config/jenkins", json={"url": "http://jenkins", "user": "bob", "token": "jeton-tres-secret"}, headers=headers).status_code == 200
    event = last(client, headers, "integration.save")
    assert event["actor_role"] == "security_officer" and event["target_id"] == "jenkins"
    assert json.loads(event["after"]) == {"jenkins_url": "http://jenkins", "jenkins_user": "bob", "jenkins_token": "***"}
    assert "jeton-tres-secret" not in json.dumps(event)

    # Même URL renvoyée sans jeton : rien n'a changé, l'action reste tracée, le diff est vide.
    assert client.post("/api/config/sonarqube", json={"url": "http://sonar"}, headers=headers).status_code == 200
    assert client.post("/api/config/sonarqube", json={"url": "http://sonar"}, headers=headers).status_code == 200
    sonar = events(client, headers, action="integration.save", target_type="integration")[0]
    assert sonar["target_id"] == "sonarqube" and json.loads(sonar["after"]) == {}


def test_reglages_globaux_modules_politiques_et_pipelines(client, monkeypatch):
    headers = login(client, "admin")
    assert client.post("/api/config", json={"anomaly_block_threshold": 0.9}, headers=headers).status_code == 200
    assert json.loads(last(client, headers, "settings.save")["after"]) == {"anomaly_block_threshold": 0.9}

    assert client.post("/api/modules/notifications/toggle", headers=headers).status_code == 200
    module = last(client, headers, "module.toggle")
    assert module["target_id"] == "notifications" and json.loads(module["after"]) == {"is_active": False}

    r = client.post("/api/compliance-policies", json={"name": "Fenêtre", "policy_type": "DEPLOYMENT_WINDOW", "allowed_days": "1,2,3"}, headers=headers)
    assert r.status_code == 200
    created = last(client, headers, "policy.create")
    assert created["target_label"] == "Fenêtre" and json.loads(created["after"])["policy_type"] == "DEPLOYMENT_WINDOW"
    assert client.delete(f"/api/compliance-policies/{r.json()['id']}", headers=headers).status_code == 200
    assert json.loads(last(client, headers, "policy.delete")["before"])["name"] == "Fenêtre"

    async def no_provisioning(db, config):
        return []

    monkeypatch.setattr(pipeline_configs, "_auto_provision", no_provisioning)
    r = client.post("/api/pipeline-configs", json={"repository": "api", "webhook_secret": "un-secret-de-webhook-long"}, headers=headers)
    assert r.status_code == 200, r.text
    pipeline = last(client, headers, "pipeline.create")
    assert pipeline["target_label"] == "api" and json.loads(pipeline["after"])["webhook_secret"] == "***"
    assert "un-secret-de-webhook-long" not in json.dumps(pipeline)
    assert client.patch(f"/api/pipeline-configs/{r.json()['id']}", json={"repository": "api", "is_active": False}, headers=headers).status_code == 200
    assert json.loads(last(client, headers, "pipeline.update")["after"]) == {"is_active": False}


def test_creer_et_revoquer_un_jeton_api_laisse_une_trace_sans_le_jeton(client):
    """
    Créer un compte de service de rôle administrateur est l'action la plus
    privilégiée de l'application : elle ne peut pas être la seule à ne rien
    laisser dans la chaîne.
    """
    headers = login(client, "admin")
    # Action privilégiée : la session ne suffit pas, le mot de passe est confirmé.
    r = client.post("/api/api-tokens", json={"name": "jenkins-ci", "role": "admin", "expires_in_days": 30},
                    headers={**headers, "X-Confirm-Password": PASSWORD})
    assert r.status_code == 200
    jeton = r.json()["token"]

    created = last(client, headers, "api_token.create")
    assert created["target_label"] == "jenkins-ci" and json.loads(created["after"])["role"] == "admin"
    assert jeton not in json.dumps(created)

    assert client.post(f"/api/api-tokens/{r.json()['id']}/revoke", headers=headers).status_code == 200
    revoked = last(client, headers, "api_token.revoke")
    assert json.loads(revoked["after"]) == {"is_revoked": True}


# --- accès et intégrité ------------------------------------------------------------

def test_le_journal_est_reserve_aux_administrateurs_et_responsables_securite(client):
    assert client.get("/api/audit/admin-events", headers=login(client, "dev")).status_code == 403
    assert client.get("/api/audit/admin-events", headers=login(client, "rssi")).status_code == 200


def test_la_chaine_se_verifie_et_detecte_une_alteration(client, db):
    headers = login(client, "admin")
    client.post("/api/modules/notifications/toggle", headers=headers)
    client.post("/api/modules/notifications/toggle", headers=headers)
    assert client.get("/api/audit/admin-events/verify", headers=headers).json()["status"] == "intact"

    with Session(db) as s:
        s.execute(text("UPDATE admin_events SET actor = 'quelqu-un-d-autre' WHERE action = 'module.toggle' AND id = (SELECT MIN(id) FROM admin_events WHERE action = 'module.toggle')"))
        s.commit()
        assert verify_admin_chain(s)[0] is False
    r = client.get("/api/audit/admin-events/verify", headers=headers).json()
    assert r["status"] == "corrupted" and r["first_corrupted_entry_id"] == 2
    # La chaîne des décisions, elle, n'est pas concernée.
    assert client.get("/api/audit/verify", headers=headers).json()["status"] == "intact"


def test_les_deux_chaines_ne_partagent_pas_leurs_sceaux():
    entry = {"timestamp": "t", "actor": "admin", "action": "user.create"}
    key = b"k" * 32
    entry["entry_hash"] = seal(entry, None, key=key, schema=ADMIN_SEAL)
    assert verify_chain([entry], key=key, schema=ADMIN_SEAL) == (True, None)
    assert verify_chain([entry], key=key, schema=DECISION_SEAL)[0] is False


@pytest.mark.parametrize("field", ["actor", "action", "after", "ip"])
def test_chaque_champ_scelle_compte(field):
    assert field in ADMIN_SEAL.fields(ADMIN_SEAL.current)
