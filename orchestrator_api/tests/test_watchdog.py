"""
Chien de garde : un pipeline figé finit en échec, jamais en travail éternel.

PENDING et DEPLOYING sont posés avant que le job ne tourne. Worker arrêté ou
job perdu, l'ancien code laissait le pipeline dans cet état indéfiniment.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.config import get_settings
from app.domain.pipeline_status import PipelineStatus
from app.models.audit import AuditLog
from app.models.pipeline import Pipeline
from app.orchestration.watchdog import sweep_stalled_pipelines


def vieux_pipeline(session: Session, status: str, minutes: int) -> int:
    row = Pipeline(
        repository="demo",
        branch="main",
        commit_id="c" * 40,
        commit_message="feat",
        author="dev",
        status=status,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes),
    )
    session.add(row)
    session.commit()
    return row.id


@pytest.fixture
def session(db):
    with Session(db) as s:
        yield s


@pytest.fixture
def delai() -> int:
    return get_settings().pipeline_stall_minutes


def test_une_analyse_jamais_prise_finit_en_echec(session, delai):
    pipeline_id = vieux_pipeline(session, PipelineStatus.PENDING.value, delai + 1)
    assert sweep_stalled_pipelines(session) == [pipeline_id]
    session.expire_all()
    pipeline = session.get(Pipeline, pipeline_id)
    assert pipeline.status == PipelineStatus.ANALYSIS_FAILED.value
    assert "job a probablement été perdu" in pipeline.execution_log


def test_un_deploiement_perdu_finit_en_echec_et_se_scelle(session, delai):
    """Autorisé puis jamais constaté : le journal ne peut pas s'arrêter sur « autorisé »."""
    pipeline_id = vieux_pipeline(session, PipelineStatus.DEPLOYING.value, delai + 1)
    assert sweep_stalled_pipelines(session) == [pipeline_id]
    session.expire_all()
    assert session.get(Pipeline, pipeline_id).status == PipelineStatus.DEPLOY_FAILED.value
    entry = session.exec(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert entry.decision == PipelineStatus.DEPLOY_FAILED.value and entry.commit_hash == "c" * 40


def test_un_pipeline_recent_n_est_pas_touche(session, delai):
    pipeline_id = vieux_pipeline(session, PipelineStatus.PENDING.value, delai - 5)
    assert sweep_stalled_pipelines(session) == []
    assert session.get(Pipeline, pipeline_id).status == PipelineStatus.PENDING.value


@pytest.mark.parametrize("status", [PipelineStatus.WAITING_HUMAN.value, PipelineStatus.DEROGATION_PENDING.value])
def test_une_attente_humaine_n_expire_jamais(session, delai, status):
    """Une validation peut prendre des jours : aucun délai ne doit la transformer en échec."""
    pipeline_id = vieux_pipeline(session, status, delai * 10)
    assert sweep_stalled_pipelines(session) == []
    assert session.get(Pipeline, pipeline_id).status == status


@pytest.mark.parametrize("status", [PipelineStatus.DEPLOYED.value, PipelineStatus.BLOCKED.value])
def test_un_etat_definitif_n_est_pas_rouvert(session, delai, status):
    pipeline_id = vieux_pipeline(session, status, delai * 10)
    assert sweep_stalled_pipelines(session) == []
    assert session.get(Pipeline, pipeline_id).status == status
