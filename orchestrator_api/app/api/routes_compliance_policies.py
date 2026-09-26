from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.deps import require_module, require_roles
from app.models.compliance_policy import CompliancePolicy
from app.models.user import User, UserRole
from app.services import admin_audit

router = APIRouter(dependencies=[Depends(require_module("compliance_policies"))])

_ALLOWED_ROLES = (UserRole.ADMIN, UserRole.SECURITY_OFFICER)
_JOURNALED = ("name", "policy_type", "is_active", "allowed_days", "allowed_start_hour", "allowed_end_hour", "repository_scope", "repository_pattern")


@router.get("")
def list_policies(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    return db.exec(select(CompliancePolicy).order_by(CompliancePolicy.created_at.desc())).all()  # type: ignore[arg-type]


@router.post("")
def create_policy(
    policy: CompliancePolicy,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    policy.id = None
    policy.created_by = user.username
    db.add(policy)
    db.flush()
    admin_audit.record(
        db, user, "policy.create", target_type="policy", target_id=policy.id, target_label=policy.name,
        after=admin_audit.snapshot(policy, *_JOURNALED), request=request,
    )
    db.refresh(policy)
    return policy


@router.post("/{policy_id}/toggle")
def toggle_policy(
    policy_id: int,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    policy = db.get(CompliancePolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Politique introuvable.")
    policy.is_active = not policy.is_active
    db.add(policy)
    admin_audit.record(
        db, user, "policy.toggle", target_type="policy", target_id=policy.id, target_label=policy.name,
        before={"is_active": not policy.is_active}, after={"is_active": policy.is_active}, request=request,
    )
    return {"id": policy.id, "is_active": policy.is_active}


@router.delete("/{policy_id}")
def delete_policy(
    policy_id: int,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    policy = db.get(CompliancePolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Politique introuvable.")
    before = admin_audit.snapshot(policy, *_JOURNALED)
    db.delete(policy)
    admin_audit.record(db, user, "policy.delete", target_type="policy", target_id=policy_id, target_label=before["name"], before=before, request=request)
    return {"status": "success"}
