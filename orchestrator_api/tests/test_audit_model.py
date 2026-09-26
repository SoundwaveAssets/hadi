"""
Bascule SHA-256 -> HMAC du journal réel (models/audit.py), sur SQLite en
mémoire : entrées héritées, ancrage de genèse, puis entrées HMAC.
"""
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.core.audit_seal as seal_module
from app.models.audit import AuditLog, append_audit_log, compute_legacy_hash, verify_chain_integrity


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(seal_module, "_GENESIS_FILE", tmp_path / "audit.genesis")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=[AuditLog.__table__])
    with Session(engine) as s:
        yield s


def entry(n: int, decision: str = "AUTO_AUTH") -> AuditLog:
    return AuditLog(developer_username="ada", repository_name="demo", commit_hash=f"c{n:04d}", decision=decision, justification="ok")


def legacy_append(session: Session, e: AuditLog) -> AuditLog:
    """Ce que faisait l'ancien append_audit_log : SHA-256 nu, sans clé."""
    last = session.exec(select(AuditLog).order_by(AuditLog.id.desc())).first()
    e.previous_hash = last.entry_hash if last else None
    e.entry_hash = compute_legacy_hash(e, e.previous_hash)
    session.add(e)
    session.commit()
    session.refresh(e)
    return e


def test_journal_herite_reste_verifiable_sans_genese(session):
    for i in range(3):
        legacy_append(session, entry(i))
    assert verify_chain_integrity(session) == (True, None)


def test_premiere_ecriture_hmac_ancre_la_fin_de_l_heritage(session):
    for i in range(3):
        legacy_append(session, entry(i))
    new = append_audit_log(session, entry(3))
    genesis = seal_module.read_genesis()
    assert genesis["id"] == 3
    assert new.entry_hash != compute_legacy_hash(new, new.previous_hash)
    assert verify_chain_integrity(session) == (True, None)


def test_installation_neuve_tout_en_hmac(session):
    append_audit_log(session, entry(0))
    append_audit_log(session, entry(1))
    assert seal_module.read_genesis()["id"] == 0
    assert verify_chain_integrity(session) == (True, None)


def test_alteration_d_une_entree_heritee_detectee(session):
    for i in range(3):
        legacy_append(session, entry(i))
    append_audit_log(session, entry(3))
    second = session.get(AuditLog, 2)
    second.decision = "BLOCKED"
    session.add(second)
    session.commit()
    assert verify_chain_integrity(session) == (False, 2)


def test_alteration_d_une_entree_hmac_detectee(session):
    append_audit_log(session, entry(0))
    append_audit_log(session, entry(1))
    e = session.get(AuditLog, 2)
    e.justification = "dérogation silencieuse"
    session.add(e)
    session.commit()
    assert verify_chain_integrity(session) == (False, 2)


def test_rescellement_avec_l_ancien_algorithme_refuse(session):
    """L'attaque que le SHA-256 nu laissait passer : réécrire la queue de chaîne sans clé."""
    legacy_append(session, entry(0))
    append_audit_log(session, entry(1))
    append_audit_log(session, entry(2))
    for e in session.exec(select(AuditLog).where(AuditLog.id >= 2).order_by(AuditLog.id)).all():
        e.decision = "AUTO_AUTH" if e.id == 2 else e.decision
        e.entry_hash = compute_legacy_hash(e, e.previous_hash)
        session.add(e)
    session.commit()
    intact, faulty = verify_chain_integrity(session)
    assert not intact and faulty == 2
