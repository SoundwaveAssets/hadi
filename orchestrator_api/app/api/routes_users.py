from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.deps import require_password_confirmation, require_roles
from app.core.passwords import Password
from app.core.security import hash_password
from app.models.forge_identity import ForgeIdentity
from app.models.user import User, UserRole
from app.providers import PROVIDERS
from app.services import admin_audit

router = APIRouter()


def _serialize(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
    }


@router.get("")
def list_users(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Gestion des rôles et permissions, vue d'ensemble des comptes."""
    users = db.exec(select(User).order_by(User.id.asc())).all()  # type: ignore[arg-type]
    return [_serialize(u) for u in users]


class CreateUserPayload(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")
    email: Optional[EmailStr] = None
    password: Password
    role: UserRole


@router.post("")
def create_user(
    payload: CreateUserPayload,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    existing = db.exec(select(User).where(User.username == payload.username)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe déjà.")

    # Le nouveau compte doit changer ce mot de passe initial à sa première
    # connexion, même logique que le compte admin/admin semé à l'installation.
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    admin_audit.record(
        db, admin, "user.create", target_type="user", target_id=user.id, target_label=user.username,
        after=admin_audit.snapshot(user, "username", "email", "role", "is_active"), request=request,
    )
    db.refresh(user)
    return _serialize(user)


class UpdateUserPayload(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    payload: UpdateUserPayload,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    if user.id == admin.id and (payload.is_active is False or (payload.role and payload.role != UserRole.ADMIN)):
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas retirer vos propres droits d'administrateur.")

    if payload.is_active is False or (payload.role and payload.role != UserRole.ADMIN and user.role == UserRole.ADMIN):
        remaining_admins = db.exec(
            select(User).where(User.role == UserRole.ADMIN, User.is_active == True, User.id != user.id)  # noqa: E712
        ).all()
        if not remaining_admins:
            raise HTTPException(
                status_code=400, detail="Impossible : ce compte est le dernier administrateur actif."
            )

    before = admin_audit.snapshot(user, "role", "is_active")
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.add(user)
    before, after = admin_audit.diff(before, admin_audit.snapshot(user, "role", "is_active"))
    admin_audit.record(
        db, admin, "user.update", target_type="user", target_id=user.id, target_label=user.username,
        before=before, after=after, request=request,
    )
    db.refresh(user)
    return _serialize(user)


class ResetPasswordPayload(BaseModel):
    new_password: Password


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: ResetPasswordPayload,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    _: User = Depends(require_password_confirmation),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    user.hashed_password = hash_password(payload.new_password)
    user.must_change_password = True
    # Réinitialiser, c'est aussi lever un verrouillage anti-brute-force en cours.
    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    admin_audit.record(db, admin, "user.reset_password", target_type="user", target_id=user.id, target_label=user.username, request=request)
    return {"status": "success", "message": f"Mot de passe de {user.username} réinitialisé."}


# --- Identités de forge --------------------------------------------------------
# Un login de forge relié à un compte rend un push attribuable (voir
# domain/identity.py). Relié par un administrateur, jamais revendiqué.
class ForgeIdentityPayload(BaseModel):
    provider: str
    login: str = Field(min_length=1, max_length=255)
    external_id: Optional[str] = Field(default=None, max_length=64)


def _serialize_identity(identity: ForgeIdentity) -> dict:
    return {
        "id": identity.id,
        "user_id": identity.user_id,
        "provider": identity.provider,
        "login": identity.login,
        "external_id": identity.external_id,
        "created_at": identity.created_at,
    }


@router.get("/{user_id}/identities")
def list_identities(
    user_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    rows = db.exec(select(ForgeIdentity).where(ForgeIdentity.user_id == user_id).order_by(ForgeIdentity.id)).all()  # type: ignore[arg-type]
    return [_serialize_identity(r) for r in rows]


@router.post("/{user_id}/identities")
def add_identity(
    user_id: int,
    payload: ForgeIdentityPayload,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    if payload.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Forge inconnue.")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    login = payload.login.strip()
    taken = db.exec(select(ForgeIdentity).where(ForgeIdentity.provider == payload.provider, ForgeIdentity.login == login)).first()
    if taken:
        raise HTTPException(status_code=409, detail=f"Le compte {payload.provider} « {login} » est déjà relié à un utilisateur.")
    identity = ForgeIdentity(user_id=user_id, provider=payload.provider, login=login, external_id=payload.external_id or None)
    db.add(identity)
    admin_audit.record(
        db, admin, "user.identity.add", target_type="user", target_id=user.id, target_label=user.username,
        after=admin_audit.snapshot(identity, "provider", "login", "external_id"), request=request,
    )
    db.refresh(identity)
    return _serialize_identity(identity)


@router.delete("/{user_id}/identities/{identity_id}")
def remove_identity(
    user_id: int,
    identity_id: int,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    identity = db.get(ForgeIdentity, identity_id)
    if not identity or identity.user_id != user_id:
        raise HTTPException(status_code=404, detail="Identité introuvable.")
    before = admin_audit.snapshot(identity, "provider", "login", "external_id")
    db.delete(identity)
    user = db.get(User, user_id)
    admin_audit.record(
        db, admin, "user.identity.remove", target_type="user", target_id=user_id, target_label=user.username if user else None,
        before=before, request=request,
    )
    return {"status": "success"}
