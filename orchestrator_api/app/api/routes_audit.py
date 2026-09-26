from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.deps import require_module, require_roles
from app.models.admin_event import AdminEvent, verify_admin_chain
from app.models.audit import AuditLog, verify_chain_integrity
from app.models.user import User, UserRole

router = APIRouter()


@router.get("", dependencies=[Depends(require_module("audit"))])
def list_audit_entries(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    decision: Optional[str] = Query(default=None),
    repository: Optional[str] = Query(default=None),
    developer: Optional[str] = Query(default=None),
):
    """
    Navigateur paginé/filtrable du journal d'audit complet, pas seulement
    la file d'attente (/pending) ou l'historique d'un commit (/history) :
    toute décision jamais prise, consultable par le Responsable sécurité.
    """
    query = select(AuditLog).order_by(AuditLog.id.desc())  # type: ignore[arg-type]
    if decision:
        query = query.where(AuditLog.decision == decision)
    if repository:
        query = query.where(AuditLog.repository_name.contains(repository))
    if developer:
        query = query.where(AuditLog.developer_username.contains(developer))
    return _page(db, query, limit, offset)


def _page(db: Session, query, limit: int, offset: int) -> dict:
    total = db.exec(select(func.count()).select_from(query.subquery())).one()
    entries = db.exec(query.offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset, "entries": entries}


@router.get("/verify")
def verify_audit_chain(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    """
    Rejoue la chaîne de hash du journal d'audit et confirme qu'aucune entrée
    n'a été modifiée ou supprimée rétroactivement.
    """
    is_intact, corrupted_id = verify_chain_integrity(db)
    if is_intact:
        return {"status": "intact", "message": "Le journal d'audit est intact et vérifié."}
    return {
        "status": "corrupted",
        "message": f"Rupture de la chaîne d'intégrité détectée à partir de l'entrée #{corrupted_id}.",
        "first_corrupted_entry_id": corrupted_id,
    }


# --- Journal des actions d'administration (models/admin_event.py) ---------------
@router.get("/admin-events", dependencies=[Depends(require_module("audit"))])
def list_admin_events(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None, description="Préfixe : `user.` renvoie toutes les actions sur les comptes"),
    target_type: Optional[str] = Query(default=None),
):
    query = select(AdminEvent).order_by(AdminEvent.id.desc())  # type: ignore[arg-type]
    if actor:
        query = query.where(AdminEvent.actor.contains(actor))
    if action:
        query = query.where(AdminEvent.action.startswith(action))
    if target_type:
        query = query.where(AdminEvent.target_type == target_type)
    return _page(db, query, limit, offset)


@router.get("/admin-events/verify")
def verify_admin_events(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    is_intact, corrupted_id = verify_admin_chain(db)
    if is_intact:
        return {"status": "intact", "message": "Le journal des actions d'administration est intact et vérifié."}
    return {
        "status": "corrupted",
        "message": f"Rupture de la chaîne d'intégrité détectée à partir de l'événement #{corrupted_id}.",
        "first_corrupted_entry_id": corrupted_id,
    }
