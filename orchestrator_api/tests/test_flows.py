"""
Enchaînements d'analyse et de déploiement.

C'est ici que se décide DEPLOYED contre DEPLOY_FAILED, et c'est ce que la
suite ne couvrait pas : les règles pures étaient testées, le chemin qui les
applique ne l'était pas. Les étapes externes (Jenkins, SonarQube, Argo CD,
Git) sont remplacées ; tout le reste est le vrai code, sur la vraie base.
"""
import pytest
from sqlmodel import Session, select

import app.orchestration.flows as flows
from app.domain.decision import UNVERIFIABLE
from app.models.audit import AuditLog
from app.models.pipeline import Pipeline

COMMIT = "a" * 40


@pytest.fixture
def pipeline(db) -> int:
    with Session(db) as s:
        row = Pipeline(repository="demo", branch="main", commit_id=COMMIT, commit_message="feat", author="dev", status="PENDING")
        s.add(row)
        s.commit()
        return row.id


@pytest.fixture
def étapes(monkeypatch):
    """Toutes les étapes externes neutralisées ; chaque test ne redéfinit que ce qui l'intéresse."""
    appels: dict[str, list] = {"deploiement": []}

    async def build(repository, commit_hash, pipeline_id=None):
        return {"success": True, "build_number": 42}

    async def scan(repository, commit_hash):
        return {"vulnerabilities": 0, "new_vulnerabilities": 0, "bugs": 0, "quality_gate": "OK"}

    async def enqueue(pipeline_id, repository, commit_hash, audit_id):
        appels["deploiement"].append((pipeline_id, repository, commit_hash, audit_id))
        return 1

    monkeypatch.setattr(flows, "trigger_jenkins_build", build)
    monkeypatch.setattr(flows, "run_sonarqube_scan", scan)
    monkeypatch.setattr("app.orchestration.jobs.enqueue_deployment", enqueue)
    return appels


def état(db, pipeline_id: int) -> Pipeline:
    with Session(db) as s:
        return s.get(Pipeline, pipeline_id)


def journal(db, pipeline_id: int) -> str:
    return état(db, pipeline_id).execution_log or ""


# --- analyse ------------------------------------------------------------------------

@pytest.mark.anyio
async def test_analyse_propre_autorise_et_met_le_deploiement_en_file(db, pipeline, étapes):
    decision = await flows.security_analysis_flow(pipeline, "demo", COMMIT, "dev", {})
    assert decision == "AUTO_AUTH"
    assert état(db, pipeline).status == "DEPLOYING"  # jamais DEPLOYED avant le déploiement réel
    assert état(db, pipeline).jenkins_build_number == 42
    assert len(étapes["deploiement"]) == 1


@pytest.mark.anyio
async def test_build_en_echec_bloque_sans_interroger_sonarqube(db, pipeline, étapes, monkeypatch):
    async def build_rate(repository, commit_hash, pipeline_id=None):
        return {"success": False, "build_number": 7}

    async def scan_interdit(repository, commit_hash):
        pytest.fail("aucune analyse ne doit être attendue quand le build a échoué")

    monkeypatch.setattr(flows, "trigger_jenkins_build", build_rate)
    monkeypatch.setattr(flows, "run_sonarqube_scan", scan_interdit)

    assert await flows.security_analysis_flow(pipeline, "demo", COMMIT, "dev", {}) == "BLOCKED"
    assert état(db, pipeline).status == "BLOCKED"
    assert not étapes["deploiement"]


@pytest.mark.anyio
async def test_sonarqube_injoignable_ne_passe_pas_pour_un_projet_propre(db, pipeline, étapes, monkeypatch):
    async def scan_absent(repository, commit_hash):
        return {"vulnerabilities": UNVERIFIABLE, "new_vulnerabilities": UNVERIFIABLE, "analysis_missing": True}

    monkeypatch.setattr(flows, "run_sonarqube_scan", scan_absent)

    assert await flows.security_analysis_flow(pipeline, "demo", COMMIT, "dev", {}) == "WAITING_HUMAN"
    assert état(db, pipeline).status == "WAITING_HUMAN"
    assert "aucune analyse attribuable" in journal(db, pipeline)
    with Session(db) as s:
        entry = s.exec(select(AuditLog).order_by(AuditLog.id.desc())).first()
        assert "non vérifiable" in entry.justification


@pytest.mark.anyio
async def test_une_panne_inattendue_laisse_une_trace_pas_un_pipeline_fantome(db, pipeline, étapes, monkeypatch):
    """Sans ce filet, une exception laissait le pipeline en PENDING sans explication."""
    async def build_explose(repository, commit_hash, pipeline_id=None):
        raise RuntimeError("agent Jenkins introuvable")

    monkeypatch.setattr(flows, "trigger_jenkins_build", build_explose)
    monkeypatch.setattr(flows, "evaluate_pipeline_and_decide", _explose)

    assert await flows.security_analysis_flow(pipeline, "demo", COMMIT, "dev", {}) == "ANALYSIS_FAILED"
    assert état(db, pipeline).status == "ANALYSIS_FAILED"
    assert "Échec inattendu" in journal(db, pipeline)


async def _explose(*args, **kwargs):
    raise RuntimeError("moteur de décision indisponible")


# --- déploiement --------------------------------------------------------------------

@pytest.fixture
def deploiement(monkeypatch):
    """Chaîne de déploiement au vert ; chaque test casse une étape et une seule."""
    async def build_pousse(repository, commit_hash, existing_build_number, pipeline_id=None):
        return True

    async def manifeste(repository, commit_hash, audit_id=None):
        return {"revision": "b" * 40, "image_ref": f"registre/demo:{commit_hash[:7]}"}

    async def sync(repository, revision):
        return True

    async def image_observee(repository, image_ref):
        return True

    monkeypatch.setattr(flows, "ensure_build_pushed", build_pousse)
    monkeypatch.setattr(flows, "write_release_manifest", manifeste)
    monkeypatch.setattr(flows, "trigger_argocd_sync", sync)
    monkeypatch.setattr(flows, "verify_deployed_image", image_observee)


@pytest.mark.anyio
async def test_deploiement_complet_pose_deployed(db, pipeline, deploiement):
    assert await flows.deployment_flow(pipeline, "demo", COMMIT) is True
    assert état(db, pipeline).status == "DEPLOYED"
    assert "observée sur le cluster" in journal(db, pipeline)


@pytest.mark.anyio
async def test_l_acte_de_deploiement_entre_dans_le_journal_scelle(db, pipeline, deploiement):
    """
    Le journal prouvait la décision, pas l'acte. Réussite comme échec
    laissent désormais une entrée scellée, vérifiable avec le reste.
    """
    from app.models.audit import verify_chain_integrity

    await flows.deployment_flow(pipeline, "demo", COMMIT)
    with Session(db) as s:
        entry = s.exec(select(AuditLog).order_by(AuditLog.id.desc())).first()
        assert entry.decision == "DEPLOYED"
        assert entry.repository_name == "demo" and entry.commit_hash == COMMIT and entry.developer_username == "dev"
        assert "observée sur l'application Argo CD" in entry.justification
        assert verify_chain_integrity(s) == (True, None)


@pytest.mark.anyio
async def test_un_echec_de_deploiement_est_scelle_avec_sa_raison(db, pipeline, deploiement, monkeypatch):
    async def sync_ratee(repository, revision):
        return False

    monkeypatch.setattr(flows, "trigger_argocd_sync", sync_ratee)
    await flows.deployment_flow(pipeline, "demo", COMMIT)
    with Session(db) as s:
        entry = s.exec(select(AuditLog).order_by(AuditLog.id.desc())).first()
        assert entry.decision == "DEPLOY_FAILED" and "Argo CD" in entry.justification


@pytest.mark.anyio
async def test_le_point_de_controle_ignore_les_issues_de_deploiement(client, db, pipeline, deploiement):
    """
    Le point de contrôle Jenkins lit la dernière DÉCISION d'un commit. Sans
    filtre, un commit déjà déployé n'aurait plus de verdict lisible et le
    job aurait expiré en 408 au lieu de reconstruire.
    """
    from app.models.audit import append_audit_log
    from tests.conftest import login

    with Session(db) as s:
        append_audit_log(s, AuditLog(developer_username="dev", repository_name="demo", commit_hash=COMMIT, decision="AUTO_AUTH", justification="vert"))
    await flows.deployment_flow(pipeline, "demo", COMMIT)

    r = client.get(f"/api/decisions/gate/demo/{COMMIT}?wait=1", headers=login(client, "admin"))
    assert r.status_code == 200 and r.json() == {"allow": True, "decision": "AUTO_AUTH"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "étape, remplacement, trace",
    [
        ("ensure_build_pushed", False, "impossible d'obtenir une image"),
        ("trigger_argocd_sync", False, "Argo CD en échec"),
        ("verify_deployed_image", False, "n'est pas observée"),
    ],
)
async def test_chaque_etape_en_echec_arrete_tout_et_dit_pourquoi(db, pipeline, deploiement, monkeypatch, étape, remplacement, trace):
    async def echoue(*args, **kwargs):
        return remplacement

    monkeypatch.setattr(flows, étape, echoue)
    assert await flows.deployment_flow(pipeline, "demo", COMMIT) is False
    assert état(db, pipeline).status == "DEPLOY_FAILED"
    assert trace in journal(db, pipeline)


@pytest.mark.anyio
async def test_un_manifeste_illisible_ne_declenche_aucune_synchronisation(db, pipeline, deploiement, monkeypatch):
    async def manifeste_casse(repository, commit_hash, audit_id=None):
        raise RuntimeError("balise RELEASE_TAG absente du manifeste")

    async def sync_interdite(repository, revision):
        pytest.fail("aucune synchronisation ne doit partir sans manifeste épinglé")

    monkeypatch.setattr(flows, "write_release_manifest", manifeste_casse)
    monkeypatch.setattr(flows, "trigger_argocd_sync", sync_interdite)

    assert await flows.deployment_flow(pipeline, "demo", COMMIT) is False
    assert état(db, pipeline).status == "DEPLOY_FAILED"
    assert "RELEASE_TAG" in journal(db, pipeline)


@pytest.mark.anyio
async def test_manifeste_deja_epingle_poursuit_la_synchronisation(db, pipeline, deploiement, monkeypatch):
    """Une dérogation relancée sur un commit déjà épinglé doit quand même aboutir."""
    async def inchange(repository, commit_hash, audit_id=None):
        return {"unchanged": True, "revision": None, "image_ref": "registre/demo:aaaaaaa"}

    monkeypatch.setattr(flows, "write_release_manifest", inchange)
    assert await flows.deployment_flow(pipeline, "demo", COMMIT) is True
    assert "déjà épinglé" in journal(db, pipeline)
    assert état(db, pipeline).status == "DEPLOYED"
