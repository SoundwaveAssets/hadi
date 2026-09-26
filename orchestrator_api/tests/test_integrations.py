"""Tests de connexion des intégrations : règles pures, forme des résultats, route /api/config/test."""
import httpx
import pytest

from app.providers.forges import auth_result
from app.services import integrations
from app.services.integrations import describe_connection_error, same_origin
from tests.conftest import login


@pytest.mark.parametrize(
    ("url", "saved", "expected"),
    [
        ("http://jenkins:8080/", "http://jenkins:8080", True),
        ("HTTP://jenkins:8080/api", "http://jenkins:8080/", True),
        ("https://jenkins:8080", "http://jenkins:8080", False),
        ("http://jenkins:8081", "http://jenkins:8080", False),
        ("http://autre:8080", "http://jenkins:8080", False),
        ("http://jenkins:8080", None, False),
    ],
)
def test_same_origin(url, saved, expected):
    assert same_origin(url, saved) is expected


def test_erreur_tls_sur_un_serveur_http():
    message = describe_connection_error("https://sonar:9000", Exception("SSL: WRONG_VERSION_NUMBER"))
    assert "http://sonar:9000" in message


def test_erreurs_reseau_courantes():
    assert "Délai dépassé" in describe_connection_error("http://x", httpx.ConnectTimeout("t"))
    assert "Connexion refusée" in describe_connection_error("http://x", httpx.ConnectError("c"))
    assert "Injoignable" in describe_connection_error("http://x", RuntimeError("autre"))


def test_auth_result_couvre_les_trois_issues():
    assert auth_result(200)["code"] == "auth_ok"
    assert auth_result(200, authenticated=False)["code"] == "no_auth"
    assert auth_result(401)["code"] == "auth_refused"
    assert auth_result(500)["reachable"] is False


@pytest.mark.anyio
async def test_outil_inconnu():
    with pytest.raises(ValueError):
        await integrations.test_tool("bazar", "http://x", None, None)


@pytest.mark.anyio
async def test_panne_reseau_devient_un_resultat_lisible(monkeypatch):
    async def boom(url, user, token):
        raise httpx.ConnectError("refusée")

    monkeypatch.setattr("app.services.integrations.test_jenkins", boom)
    result = await integrations.test_tool("jenkins", "http://jenkins:8080", None, None)
    assert result["code"] == "network" and result["reachable"] is False


def test_route_test_outil_inconnu(client):
    headers = login(client, "admin")
    r = client.post("/api/config/test/bazar", json={"url": "http://x"}, headers=headers)
    assert r.status_code == 400


def test_l_etat_des_integrations_compte_les_profils_appris(client, db):
    """La carte « IA » de la page Intégrations lit les profils en base, plus un fichier local."""
    from sqlmodel import Session

    from app.ai.store import ProfileStore

    with Session(db) as session:
        ProfileStore(session).record_push("dev", [14.0, 3.0, 1.0, 0.0], {"a.py"})

    health = client.get("/api/config/health", headers=login(client, "admin")).json()
    assert health["ai"]["message"].startswith("1 profil(s) de développeur appris sur 1 push(s)")
    assert health["database"] == {"configured": True, "reachable": True}


# --- exécutable de la CLI --------------------------------------------------------

def test_l_empreinte_accompagne_l_executable(client, tmp_path, monkeypatch):
    """Ce qui est servi et ce qui est annoncé sont le même octet : même condensat des deux côtés."""
    import hashlib

    from app.services import cli_artifacts

    binary = tmp_path / "hadi-linux"
    binary.write_bytes(b"binaire de test")
    monkeypatch.setattr(cli_artifacts, "_DIST_DIR", tmp_path)
    attendu = hashlib.sha256(b"binaire de test").hexdigest()

    headers = login(client, "dev")
    annonce = client.get("/api/cli/checksum", params={"os": "linux"}, headers=headers).json()
    assert annonce["sha256"] == attendu and annonce["filename"] == "hadi" and "sha256sum" in annonce["command"]

    served = client.get("/api/cli/download", params={"os": "linux"}, headers=headers)
    assert served.headers["x-checksum-sha256"] == attendu
    assert hashlib.sha256(served.content).hexdigest() == attendu


def test_un_binaire_reconstruit_change_d_empreinte(tmp_path, monkeypatch):
    from app.services import cli_artifacts

    monkeypatch.setattr(cli_artifacts, "_DIST_DIR", tmp_path)
    binary = tmp_path / "hadi-linux"
    binary.write_bytes(b"version 1")
    premiere = cli_artifacts.find("linux").sha256

    binary.write_bytes(b"version 2 plus longue")
    assert cli_artifacts.find("linux").sha256 != premiere


def test_plateforme_inconnue_et_binaire_absent(client, tmp_path, monkeypatch):
    from app.services import cli_artifacts

    monkeypatch.setattr(cli_artifacts, "_DIST_DIR", tmp_path)
    headers = login(client, "dev")
    assert client.get("/api/cli/checksum", params={"os": "bsd"}, headers=headers).status_code == 400
    assert client.get("/api/cli/checksum", params={"os": "../etc"}, headers=headers).status_code == 400
    assert client.get("/api/cli/download", params={"os": "linux"}, headers=headers).status_code == 404


# --- lecture des métriques SonarQube ------------------------------------------------

def test_une_mesure_de_code_neuf_se_lit_dans_period_ou_periods():
    """
    Les métriques new_* n'ont pas de `value` : SonarQube les renvoie dans
    `period` (8+) ou `periods[0]` (antérieur). Ne lire que `value`, c'était
    conclure « non vérifiable » sur toutes, donc mettre chaque push en attente.
    """
    from app.services.sonarqube_client import SonarQubeClient

    mesures = SonarQubeClient._measures([
        {"metric": "vulnerabilities", "value": "40"},
        {"metric": "new_vulnerabilities", "period": {"index": 1, "value": "0"}},
        {"metric": "new_coverage", "periods": [{"index": 1, "value": "82.5"}]},
        {"metric": "new_bugs"},
    ])
    assert mesures == {"vulnerabilities": "40", "new_vulnerabilities": "0", "new_coverage": "82.5"}


def test_le_critere_effectif_vient_du_pipeline_puis_du_global_puis_du_defaut():
    from types import SimpleNamespace

    from app.decision_engine import _resolve_criterion
    from app.domain.decision import SecurityCriterion

    globale = SimpleNamespace(security_criterion="total")
    assert _resolve_criterion(SimpleNamespace(security_criterion="quality_gate"), globale) is SecurityCriterion.QUALITY_GATE
    assert _resolve_criterion(SimpleNamespace(security_criterion=None), globale) is SecurityCriterion.TOTAL
    assert _resolve_criterion(None, None) is SecurityCriterion.NEW_CODE
    # Valeur inconnue en base : repli sur le défaut, jamais d'exception qui tuerait l'analyse.
    assert _resolve_criterion(None, SimpleNamespace(security_criterion="n-importe-quoi")) is SecurityCriterion.NEW_CODE


# --- santé des intégrations : identifiants compris ---------------------------------

def test_la_sante_verifie_le_jeton_pas_seulement_l_atteignabilite(client, db, monkeypatch):
    """
    Une tuile verte avec un jeton révoqué, c'est une panne qu'on ne découvre
    qu'au push suivant. La santé rejoue le test authentifié quand un jeton
    est enregistré.
    """
    from sqlmodel import Session

    from app.core.crypto import secret_box
    from app.models.config import ToolConfig

    with Session(db) as s:
        s.add(ToolConfig(id=1, jenkins_url="http://jenkins", jenkins_user="bob", jenkins_token=secret_box.encrypt("jeton-mort")))
        s.commit()

    vus = []

    async def jeton_refuse(url, user, token):
        vus.append((url, user, token))
        return {"reachable": True, "authenticated": False, "code": "auth_refused", "message": "Identifiants refusés."}

    monkeypatch.setattr("app.services.integrations.test_jenkins", jeton_refuse)
    health = client.get("/api/config/health", headers=login(client, "admin")).json()

    assert vus == [("http://jenkins", "bob", "jeton-mort")]
    assert health["jenkins"]["reachable"] is True and health["jenkins"]["authenticated"] is False


def test_sans_jeton_enregistre_la_sante_reste_une_atteignabilite(client, db, monkeypatch):
    from sqlmodel import Session

    from app.models.config import ToolConfig

    with Session(db) as s:
        s.add(ToolConfig(id=1, sonarqube_url="http://sonar"))
        s.commit()

    async def joignable(url):
        return {"configured": True, "reachable": True}

    monkeypatch.setattr("app.services.integrations.ping", joignable)
    health = client.get("/api/config/health", headers=login(client, "admin")).json()
    assert health["sonarqube"]["reachable"] is True and health["sonarqube"]["authenticated"] is None


# --- TLS : certificat auto-signé, cas de tout Argo CD en cluster --------------------

def test_un_probleme_de_certificat_ne_se_dit_plus_connexion_refusee():
    """
    Le message annonçait « connexion refusée ou hôte injoignable » pour un
    certificat non reconnu : l'exploitant vérifiait le port et l'adresse
    pendant que le vrai problème était le certificat.
    """
    erreur = httpx.ConnectError("('Une chaîne de certificats ... certificat racine qui n'est pas approuvé',)")
    message = describe_connection_error("https://localhost:9090", erreur)
    assert "certificat" in message.lower()
    assert "ORCHESTRATOR_TLS_SKIP_VERIFY_HOSTS=localhost:9090" in message


def test_la_verification_tls_ne_se_desactive_que_pour_les_hotes_declares(monkeypatch):
    """Jamais globalement, jamais par défaut : hôte par hôte, et c'est un choix d'exploitation."""
    import ssl

    from app.config import get_settings
    from app.core import tls

    assert tls.context_for("https://argocd.exemple").verify_mode is ssl.CERT_REQUIRED

    monkeypatch.setenv("ORCHESTRATOR_TLS_SKIP_VERIFY_HOSTS", "localhost:9090, argocd.interne")
    get_settings.cache_clear()
    try:
        assert tls.context_for("https://localhost:9090/api").verify_mode is ssl.CERT_NONE
        assert tls.context_for("https://argocd.interne").verify_mode is ssl.CERT_NONE
        # Un hôte voisin non déclaré reste vérifié : pas de contagion.
        assert tls.context_for("https://localhost:9443").verify_mode is ssl.CERT_REQUIRED
    finally:
        get_settings.cache_clear()
