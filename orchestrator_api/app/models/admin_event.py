"""
Journal des actions d'administration : qui a changé quoi, quand, depuis où.

Le journal des décisions (models/audit.py) répond à « pourquoi ce commit
a-t-il été déployé ? ». Celui-ci répond à « qui a désactivé ce module, relié
ce compte de forge, changé ce jeton Jenkins, et à quelle heure ? » : comptes,
rôles, intégrations, modules, politiques, pipelines enregistrés, connexions.
Même chaînage HMAC et même clé que le journal des décisions, mais une chaîne
distincte (domain/audit_chain.py, ADMIN_SEAL) : chacune se vérifie seule.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, Session, SQLModel, select

from app.core.audit_seal import AUDIT_KEY
from app.core.chain_lock import serialize_chain_writes
from app.domain.audit_chain import ADMIN_SEAL, seal, utc_isoformat, verify_chain


class AdminEvent(SQLModel, table=True):
    __tablename__ = "admin_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    actor: str = Field(index=True)
    actor_role: str
    #: Verbe qualifié et stable : user.create, integration.save, module.toggle, auth.login_failed…
    action: str = Field(index=True)
    target_type: str
    target_id: Optional[str] = Field(default=None)
    target_label: Optional[str] = Field(default=None)
    #: État avant / après en JSON canonique, secrets déjà masqués (services/admin_audit.py).
    before: Optional[str] = Field(default=None, sa_column=Column(Text))
    after: Optional[str] = Field(default=None, sa_column=Column(Text))
    ip: Optional[str] = Field(default=None)

    previous_hash: Optional[str] = Field(default=None)
    entry_hash: str = Field(default="")
    seal_version: int = Field(default=ADMIN_SEAL.current)


def _sealed_fields(event: AdminEvent) -> dict:
    data = {name: getattr(event, name) for name in ADMIN_SEAL.fields(event.seal_version)}
    data["timestamp"] = utc_isoformat(event.timestamp)
    # Hors sceau : ce que verify_chain lit pour vérifier et pour désigner une rupture.
    data.update(id=event.id, entry_hash=event.entry_hash, seal_version=event.seal_version)
    return data


def append_admin_event(session: Session, event: AdminEvent) -> AdminEvent:
    """
    Seule voie d'écriture. Valide la transaction en cours : appelé après le
    `session.add` de la modification décrite, l'événement et la modification
    sont écrits ensemble ou pas du tout.
    """
    serialize_chain_writes(session, "admin_events")
    last = session.exec(select(AdminEvent).order_by(AdminEvent.id.desc())).first()  # type: ignore[arg-type]
    event.previous_hash = last.entry_hash if last else None
    event.seal_version = ADMIN_SEAL.current
    event.entry_hash = seal(_sealed_fields(event), event.previous_hash, key=AUDIT_KEY, schema=ADMIN_SEAL)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def verify_admin_chain(session: Session) -> tuple[bool, Optional[int]]:
    events = session.exec(select(AdminEvent).order_by(AdminEvent.id.asc()))  # type: ignore[arg-type]
    return verify_chain((_sealed_fields(e) for e in events), key=AUDIT_KEY, schema=ADMIN_SEAL)
