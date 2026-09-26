from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.deps import require_module, require_password_confirmation, require_roles
from app.core.security import generate_api_token, hash_api_token
from app.models.api_token import ApiToken
from app.models.user import User, UserRole
from app.services import admin_audit

router = APIRouter(dependencies=[Depends(require_module("api_tokens"))])


def _serialize_token(record: ApiToken) -> dict:
    now = datetime.now(timezone.utc)
    expires_at = record.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    is_expired = bool(expires_at and expires_at <= now)
    return {
        "id": record.id,
        "name": record.name,
        "token_prefix": record.token_prefix,
        "role": record.role.value,
        "created_by": record.created_by,
        "created_at": record.created_at,
        "last_used_at": record.last_used_at,
        "expires_at": record.expires_at,
        "is_revoked": record.is_revoked,
        "revoked_at": record.revoked_at,
        "is_expired": is_expired,
    }


@router.get("")
def list_tokens(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    """
    Jamais le jeton lui-même (seul son hash est en base), juste son préfixe,
    pour l'identifier. Inclut `is_expired` pour que le Dashboard puisse
    signaler les jetons expirés sans les révoquer automatiquement.
    """
    tokens = db.exec(select(ApiToken).order_by(ApiToken.created_at.desc())).all()  # type: ignore[arg-type]
    return [_serialize_token(t) for t in tokens]


class CreateTokenPayload(BaseModel):
    name: str
    role: UserRole = UserRole.DEVELOPER
    #: Durée de validité en jours. None = pas d'expiration (déconseillé en
    #: production). Maximum 365 jours pour limiter l'impact d'un jeton compromis.
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


@router.post("")
def create_token(
    payload: CreateTokenPayload,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    _: User = Depends(require_password_confirmation),
):
    """
    Le jeton en clair n'est renvoyé qu'ici, une seule fois, même principe
    que le secret webhook Gitea. `expires_in_days` fixe la durée de validité ;
    sans cette valeur, le jeton est valide jusqu'à révocation manuelle.
    """
    raw_token = generate_api_token()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
        if payload.expires_in_days
        else None
    )
    record = ApiToken(
        name=payload.name,
        token_hash=hash_api_token(raw_token),
        token_prefix=raw_token[:12],
        role=payload.role,
        created_by=admin.username,
        expires_at=expires_at,
    )
    db.add(record)
    db.flush()
    # Le jeton lui-même n'entre jamais dans le journal : son préfixe suffit à
    # relier une action de compte de service à sa création.
    admin_audit.record(
        db, admin, "api_token.create", target_type="api_token", target_id=record.id, target_label=record.name,
        after={"role": record.role.value, "token_prefix": record.token_prefix, "expires_at": record.expires_at},
        request=request,
    )
    db.refresh(record)

    return {
        **_serialize_token(record),
        "token": raw_token,
    }


@router.post("/{token_id}/revoke")
def revoke_token(
    token_id: int,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    record = db.get(ApiToken, token_id)
    if not record:
        raise HTTPException(status_code=404, detail="Jeton introuvable.")
    if record.is_revoked:
        raise HTTPException(status_code=400, detail="Ce jeton est déjà révoqué.")
    record.is_revoked = True
    record.revoked_at = datetime.now(timezone.utc)
    db.add(record)
    admin_audit.record(
        db, admin, "api_token.revoke", target_type="api_token", target_id=record.id, target_label=record.name,
        before={"is_revoked": False}, after={"is_revoked": True}, request=request,
    )
    return {"status": "success", "message": "Jeton révoqué."}
