"""
Tests des routes HTTP sur SQLite en mémoire : connexion et verrouillage,
mot de passe par défaut, RBAC, quatre yeux, webhook (signature, dépôt
inconnu, rejeu, [skip ci], commit déjà déployé), assistant verrouillé,
validation des entrées, point de contrôle Jenkins.

Ce qui reste hors de portée de SQLite (GROUP BY date avec fuseau de
/activity) est couvert par la pile de démo, pas ici.
"""
import json

import pytest
from limits import parse
from sqlmodel import Session, select

import app.api.routes_webhooks as webhooks
from app.models.audit import AuditLog, append_audit_log
from app.models.pipeline import Pipeline
from tests.conftest import PASSWORD, gitea_push, login

# --- connexion -------------------------------------------------------------

def test_connexion_et_identite(client):
    headers = login(client, "admin")
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["username"] == "admin" and me["role"] == "admin"


def test_mauvais_mot_de_passe_reponse_uniforme(client):
    for username in ("admin", "inexistant"):
        r = client.post("/api/auth/login", json={"username": username, "password": "faux"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Nom d'utilisateur ou mot de passe incorrect."


def test_verrouillage_apres_echecs_repetes(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "dev", "password": "faux"})
    # Bon mot de passe, compte verrouillé : le titulaire l'apprend, pas un tiers.
    r = client.post("/api/auth/login", json={"username": "dev", "password": PASSWORD})
    assert r.status_code == 429
    r = client.post("/api/auth/login", json={"username": "dev", "password": "faux"})
    assert r.status_code == 401


def test_la_connexion_est_limitee_par_adresse(client):
    """
    Le verrouillage par compte ne freine pas un même mot de passe essayé sur
    cent comptes différents : la route porte donc aussi une limite par IP,
    réglable (ORCHESTRATOR_LOGIN_RATE_LIMIT).
    """
    from app.config import get_settings
    from app.core.ratelimit import limiter

    limits = limiter._route_limits["app.api.routes_auth.login"]
    assert [str(entry.limit) for entry in limits] == [str(parse(get_settings().login_rate_limit))]


def test_mot_de_passe_par_defaut_bloque_le_reste_de_l_api(client):
    headers = login(client, "neuf")
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.get("/api/decisions/pipelines", headers=headers).status_code == 403
    r = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "encore-plus-long-que-douze"}, headers=headers)
    assert r.status_code == 200
    assert client.get("/api/decisions/pipelines", headers=headers).status_code == 200


def test_nouveau_mot_de_passe_trop_court_refuse(client):
    headers = login(client, "dev")
    r = client.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "court"}, headers=headers)
    assert r.status_code == 422


# --- RBAC ---------------------------------------------------------------------

def test_sans_jeton_401(client):
    assert client.get("/api/decisions/pipelines").status_code == 401


@pytest.mark.parametrize("path", ["/api/users", "/api/audit", "/api/config", "/api/pipeline-configs", "/api/decisions/pending"])
def test_developpeur_refuse_sur_les_routes_d_administration(client, path):
    headers = login(client, "dev")
    assert client.get(path, headers=headers).status_code == 403


def test_administrateur_accede(client):
    headers = login(client, "admin")
    assert client.get("/api/users", headers=headers).status_code == 200
    assert client.get("/api/audit", headers=headers).status_code == 200


def test_developpeur_ne_voit_que_ses_pipelines(client, db):
    with Session(db) as s:
        s.add(Pipeline(repository="demo", branch="main", commit_id="aaa", commit_message="x", author="dev"))
        s.add(Pipeline(repository="demo", branch="main", commit_id="bbb", commit_message="y", author="autre"))
        s.commit()
    # La réponse est maintenant paginée : {"total": ..., "limit": ..., "offset": ..., "items": [...]}
    dev_resp = client.get("/api/decisions/pipelines", headers=login(client, "dev")).json()
    assert [p["commit_id"] for p in dev_resp["items"]] == ["aaa"]
    admin_resp = client.get("/api/decisions/pipelines", headers=login(client, "admin")).json()
    assert admin_resp["total"] == 2
    assert client.get("/api/decisions/pipelines/2", headers=login(client, "dev")).status_code == 404


# --- quatre yeux ---------------------------------------------------------------

def blocked_entry(db) -> int:
    with Session(db) as s:
        entry = append_audit_log(s, AuditLog(developer_username="dev", repository_name="demo", commit_hash="c1", decision="WAITING_HUMAN", justification="test"))
        s.add(Pipeline(repository="demo", branch="main", commit_id="c1", commit_message="x", author="dev", status="WAITING_HUMAN"))
        s.commit()
        return entry.id


def test_deux_validateurs_distincts(client, db):
    audit_id = blocked_entry(db)
    admin, rssi = login(client, "admin"), login(client, "rssi")

    first = client.post(f"/api/decisions/{audit_id}/approve", json={"justification": "ok"}, headers=admin)
    assert first.status_code == 200 and first.json()["status"] == "pending_second_approval"
    pending_id = first.json()["audit_id"]

    # Le même administrateur ne peut pas confirmer sa propre validation.
    assert client.post(f"/api/decisions/{pending_id}/approve", json={"justification": "encore"}, headers=admin).status_code == 403
    # L'entrée d'origine est remplacée, elle n'est plus actionnable.
    assert client.post(f"/api/decisions/{audit_id}/approve", json={"justification": "x"}, headers=rssi).status_code == 400

    second = client.post(f"/api/decisions/{pending_id}/approve", json={"justification": "ok"}, headers=rssi)
    assert second.status_code == 200 and second.json()["status"] == "success"
    with Session(db) as s:
        assert s.get(Pipeline, 1).status == "DEPLOYING"
        assert s.exec(select(AuditLog).order_by(AuditLog.id.desc())).first().decision == "DEROGATION"
    assert len(client.launched) == 1  # le déploiement a été mis en file


def test_un_developpeur_ne_valide_pas(client, db):
    audit_id = blocked_entry(db)
    assert client.post(f"/api/decisions/{audit_id}/approve", json={"justification": "x"}, headers=login(client, "dev")).status_code == 403


def test_la_demande_de_derogation_ne_debloque_rien(client, db):
    audit_id = blocked_entry(db)
    r = client.post(f"/api/decisions/{audit_id}/request-derogation", json={"justification": "urgent"}, headers=login(client, "dev"))
    assert r.status_code == 200
    with Session(db) as s:
        assert s.exec(select(AuditLog).order_by(AuditLog.id.desc())).first().decision == "DEROGATION_REQUESTED"
        assert s.get(Pipeline, 1).status == "WAITING_HUMAN"


# --- webhook -------------------------------------------------------------------

def test_webhook_valide_cree_le_pipeline_et_lance_l_analyse(client, db):
    body, headers = gitea_push("abc123", delivery="d-1")
    r = client.post("/api/webhooks/gitea", content=body, headers=headers)
    assert r.status_code == 200 and r.json()["analysis_triggered"] is True
    assert len(client.launched) == 1
    with Session(db) as s:
        assert s.exec(select(Pipeline)).one().commit_id == "abc123"


def test_webhook_signature_invalide_401_et_trace(client, db):
    body, headers = gitea_push("abc123")
    headers["X-Gitea-Signature"] = "0" * 64
    assert client.post("/api/webhooks/gitea", content=body, headers=headers).status_code == 401
    with Session(db) as s:
        assert s.exec(select(AuditLog)).one().decision == "REJECTED_INVALID_SIGNATURE"


def test_webhook_depot_inconnu_403_sans_entree_d_audit(client, db):
    body, headers = gitea_push("abc123")
    payload = json.loads(body)
    payload["repository"]["name"] = "inconnu"
    r = client.post("/api/webhooks/gitea", content=json.dumps(payload).encode(), headers=headers)
    assert r.status_code == 403
    with Session(db) as s:
        assert s.exec(select(AuditLog)).all() == []


def test_webhook_mauvaise_forge_pour_ce_depot(client):
    body, headers = gitea_push("abc123")
    assert client.post("/api/webhooks/github", content=body, headers=headers).status_code == 403
    assert client.post("/api/webhooks/svn", content=body, headers=headers).status_code == 404


def test_webhook_rejeu_ignore(client):
    body, headers = gitea_push("abc123", delivery="d-1")
    assert client.post("/api/webhooks/gitea", content=body, headers=headers).json()["analysis_triggered"] is True
    assert client.post("/api/webhooks/gitea", content=body, headers=headers).json()["analysis_triggered"] is False
    assert len(client.launched) == 1


def test_webhook_file_indisponible_la_livraison_reste_rejouable(client, db, monkeypatch):
    """
    La livraison n'est acquittée qu'une fois le job confié. Acquitter avant,
    c'était perdre le push : la forge relivrait, Hadi répondait « déjà
    traitée », et le pipeline restait figé en PENDING.
    """
    def file_en_panne(*args, **kwargs):
        raise RuntimeError("File de travail indisponible")

    monkeypatch.setattr(webhooks, "defer_analysis", file_en_panne)
    body, headers = gitea_push("abc123", delivery="d-panne")
    assert client.post("/api/webhooks/gitea", content=body, headers=headers).status_code == 503

    # La forge relivre : cette fois la file répond, le push est traité.
    monkeypatch.setattr(webhooks, "defer_analysis", lambda *a, **k: client.launched.append(a))
    assert client.post("/api/webhooks/gitea", content=body, headers=headers).json()["analysis_triggered"] is True
    assert len(client.launched) == 1


def test_webhook_skip_ci_ignore(client, db):
    body, headers = gitea_push("abc123", message="deploy: demo abc1234 [skip ci]")
    assert client.post("/api/webhooks/gitea", content=body, headers=headers).json()["analysis_triggered"] is False
    with Session(db) as s:
        assert s.exec(select(Pipeline)).all() == []


def test_webhook_commit_deja_deploye_non_remis_en_analyse(client, db):
    with Session(db) as s:
        s.add(Pipeline(repository="demo", branch="main", commit_id="abc123", commit_message="x", author="dev", status="DEPLOYED"))
        s.commit()
    body, headers = gitea_push("abc123")
    assert client.post("/api/webhooks/gitea", content=body, headers=headers).json()["analysis_triggered"] is False
    with Session(db) as s:
        assert s.get(Pipeline, 1).status == "DEPLOYED"


def test_webhook_corps_trop_volumineux(client):
    body, headers = gitea_push("abc123")
    r = client.post("/api/webhooks/gitea", content=body + b" " * webhooks.MAX_BODY_BYTES, headers=headers)
    assert r.status_code == 413


# --- assistant d'installation ---------------------------------------------------

def test_assistant_verrouille(client):
    assert client.get("/api/setup/status").json()["setup_locked"] is True
    r = client.post("/api/setup/complete", headers={"X-Setup-Token": "jeton-de-test"})
    assert r.status_code == 409


def test_assistant_exige_le_jeton(client):
    assert client.post("/api/setup/complete").status_code == 401
    assert client.post("/api/setup/complete", headers={"X-Setup-Token": "faux"}).status_code == 401


# --- validation des entrées -------------------------------------------------------

def test_nom_de_depot_invalide_refuse(client):
    headers = login(client, "admin")
    r = client.post("/api/pipeline-configs", json={"repository": "a b/c", "webhook_secret": "x" * 16}, headers=headers)
    assert r.status_code == 422
    r = client.post("/api/pipeline-configs", json={"repository": "ok", "webhook_secret": "court"}, headers=headers)
    assert r.status_code == 422


def test_creation_d_utilisateur_email_et_mot_de_passe_valides(client):
    headers = login(client, "admin")
    r = client.post("/api/users", json={"username": "x", "email": "pas-un-email", "password": PASSWORD, "role": "developer"}, headers=headers)
    assert r.status_code == 422
    r = client.post("/api/users", json={"username": "nouveau", "email": "n@exemple.org", "password": PASSWORD, "role": "developer"}, headers=headers)
    assert r.status_code == 200 and r.json()["must_change_password"] is True


# --- point de contrôle Jenkins -----------------------------------------------------

def test_gate_autorise_refuse_ou_expire(client, db):
    headers = login(client, "admin")
    # "aaaaaaa" : 7 caractères hexadécimaux valides, aucune décision connue → 408 (timeout).
    # "zzz" est désormais rejeté par la validation du format (422) : utiliser un hash valide.
    assert client.get("/api/decisions/gate/demo/aaaaaaa?wait=1", headers=headers).status_code == 408
    # Format invalide (non hexadécimal) → 422 Unprocessable Entity.
    assert client.get("/api/decisions/gate/demo/zzz?wait=1", headers=headers).status_code == 422
    with Session(db) as s:
        append_audit_log(s, AuditLog(developer_username="dev", repository_name="demo", commit_hash="abc1234", decision="AUTO_AUTH", justification="vert"))
        append_audit_log(s, AuditLog(developer_username="dev", repository_name="demo", commit_hash="def5678", decision="BLOCKED", justification="rouge"))
    assert client.get("/api/decisions/gate/demo/abc1234?wait=1", headers=headers).json()["allow"] is True
    assert client.get("/api/decisions/gate/demo/def5678?wait=1", headers=headers).status_code == 403


# --- sécurité de session ---------------------------------------------------------

def test_les_actions_privilegiees_exigent_le_mot_de_passe(client):
    """
    Un poste laissé ouvert ne doit pas suffire : créer un compte de service
    `admin` ou réinitialiser le mot de passe d'un tiers demande de confirmer
    le sien. La session seule ne suffit plus.
    """
    headers = login(client, "admin")
    jeton = {"name": "ci", "role": "admin"}

    refus = client.post("/api/api-tokens", json=jeton, headers=headers)
    assert refus.status_code == 401
    assert refus.json()["detail"]["code"] == "password_confirmation_required"

    assert client.post("/api/api-tokens", json=jeton, headers={**headers, "X-Confirm-Password": "mauvais"}).status_code == 401
    assert client.post("/api/api-tokens", json=jeton, headers={**headers, "X-Confirm-Password": PASSWORD}).status_code == 200

    dev_id = client.get("/api/users", headers=headers).json()[2]["id"]
    corps = {"new_password": "un-nouveau-mot-de-passe"}
    assert client.post(f"/api/users/{dev_id}/reset-password", json=corps, headers=headers).status_code == 401
    assert client.post(f"/api/users/{dev_id}/reset-password", json=corps, headers={**headers, "X-Confirm-Password": PASSWORD}).status_code == 200


def test_une_session_active_se_prolonge_et_la_politique_est_publiee(client):
    headers = login(client, "admin")
    r = client.post("/api/auth/refresh", headers=headers)
    assert r.status_code == 200 and r.json()["username"] == "admin"
    assert r.json()["access_token"]

    politique = client.get("/api/auth/session-policy").json()
    assert politique["idle_timeout_minutes"] > 0 and politique["session_minutes"] > 0


def test_garder_la_session_ouverte_allonge_la_session_et_se_journalise(client):
    """
    Option « garder la session ouverte », comme sur Jenkins : la session dure
    des jours au lieu de deux heures, et l'interface n'y applique pas le
    verrouillage par inactivité. Un audit doit pouvoir relire ce choix.
    """
    import json as _json
    from datetime import datetime, timezone

    import jwt as _jwt

    from app.config import get_settings
    from app.core.security import _JWT_SECRET, JWT_ALGORITHM

    def duree(reponse) -> float:
        charge = _jwt.decode(reponse.json()["access_token"], _JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return (datetime.fromtimestamp(charge["exp"], tz=timezone.utc) - datetime.now(timezone.utc)).total_seconds()

    courte = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    longue = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD, "remember_me": True})

    assert courte.json()["remembered"] is False
    assert longue.json()["remembered"] is True
    assert duree(longue) > duree(courte) * 10
    assert duree(longue) <= get_settings().remember_me_days * 24 * 3600 + 60

    politique = client.get("/api/auth/session-policy").json()
    assert politique["remember_me_days"] == get_settings().remember_me_days

    journal = client.get("/api/audit/admin-events", params={"action": "auth.login"}, headers=login(client, "admin")).json()["entries"]
    assert _json.loads(journal[0]["after"]) == {"remembered": False}
    assert any(_json.loads(e["after"]) == {"remembered": True} for e in journal)
