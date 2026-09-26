from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from app.config import get_settings
from app.core.database import get_session
from app.core.deps import get_authenticated_identity, get_current_user
from app.core.passwords import Password
from app.core.ratelimit import limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.services import admin_audit

router = APIRouter()

# Verrouillage par compte, en base : valable en plusieurs instances, sans
# infrastructure supplémentaire. La limite par IP le complète (voir ratelimit).
LOGIN_LOCKOUT_THRESHOLD = get_settings().login_lockout_threshold
LOGIN_LOCKOUT_MINUTES = get_settings().login_lockout_minutes

# Coût bcrypt identique que le compte existe ou non (voir login).
_DUMMY_HASH = hash_password("jamais-un-vrai-mot-de-passe")


class LoginPayload(BaseModel):
    username: str
    password: str
    #: « Garder la session ouverte » : session longue, exemptée du
    #: verrouillage par inactivité. À réserver à un poste personnel.
    remember_me: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    must_change_password: bool
    #: Vrai si cette session a été ouverte en mode « garder la session
    #: ouverte » : l'interface n'y applique pas le verrouillage par inactivité.
    remembered: bool = False


@router.post("/login", response_model=LoginResponse)
@limiter.limit(get_settings().login_rate_limit)
def login(payload: LoginPayload, request: Request, db: Session = Depends(get_session)):
    generic_error = HTTPException(status_code=401, detail="Nom d'utilisateur ou mot de passe incorrect.")

    user = db.exec(select(User).where(User.username == payload.username)).first()

    now = datetime.now(timezone.utc)
    locked_until: Optional[datetime] = None
    is_locked = False
    if user and user.locked_until:
        locked_until = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=timezone.utc)
        is_locked = locked_until > now

    # Vérifié même sur un compte verrouillé : seul le vrai titulaire doit
    # apprendre qu'il l'est, sinon la réponse trahit les comptes existants.
    # Compte inconnu : hachage factice, sinon l'absence de bcrypt (~100 ms)
    # les trahit aussi.
    hashed = user.hashed_password if user else _DUMMY_HASH
    credentials_valid = verify_password(payload.password, hashed) and bool(user) and user.is_active

    if is_locked:
        if credentials_valid:
            remaining_minutes = max(1, int((locked_until - now).total_seconds() // 60) + 1)  # type: ignore[operator]
            raise HTTPException(
                status_code=429,
                detail=f"Trop de tentatives échouées. Compte temporairement verrouillé, réessayez dans {remaining_minutes} min.",
            )
        raise generic_error

    # Journal : seuls les comptes existants sont concernés. Consigner les noms
    # inconnus ferait grossir le journal au rythme d'un attaquant et y
    # écrirait des chaînes qu'il choisit.
    if not credentials_valid:
        if user:
            user.failed_login_attempts += 1
            locked = user.failed_login_attempts >= LOGIN_LOCKOUT_THRESHOLD
            if locked:
                user.locked_until = now + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
            db.add(user)
            admin_audit.record(
                db, user, "auth.lockout" if locked else "auth.login_failed", target_type="user", target_id=user.id,
                target_label=user.username, after={"failed_login_attempts": user.failed_login_attempts}, request=request,
            )
        raise generic_error

    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    # La durée de la session fait partie de ce qu'un audit doit pouvoir relire.
    admin_audit.record(
        db, user, "auth.login", target_type="user", target_id=user.id, target_label=user.username,
        after={"remembered": bool(payload.remember_me and get_settings().remember_me_days > 0)}, request=request,
    )

    settings = get_settings()
    remembered = bool(payload.remember_me and settings.remember_me_days > 0)
    token = create_access_token(
        subject=user.username,
        role=user.role.value,
        expires_minutes=settings.remember_me_days * 24 * 60 if remembered else None,
    )
    return LoginResponse(
        access_token=token,
        username=user.username,
        role=user.role.value,
        must_change_password=user.must_change_password,
        remembered=remembered,
    )


@router.post("/refresh", response_model=LoginResponse)
def refresh(user: User = Depends(get_current_user)):
    """
    Prolonge la session d'une personne qui travaille : l'interface appelle
    cette route tant qu'il y a de l'activité. Un poste laissé ouvert cesse
    d'être prolongé, et sa session expire.
    """
    return LoginResponse(
        access_token=create_access_token(subject=user.username, role=user.role.value),
        username=user.username,
        role=user.role.value,
        must_change_password=user.must_change_password,
    )


@router.get("/session-policy")
def session_policy():
    """
    Durées appliquées par cette instance, lues par l'interface pour verrouiller
    l'écran au bon moment. Aucune donnée personnelle : accessible sans session,
    comme les autres informations d'amorçage.
    """
    settings = get_settings()
    return {
        "idle_timeout_minutes": settings.idle_timeout_minutes,
        "session_minutes": settings.jwt_expire_minutes,
        "sudo_minutes": settings.sudo_minutes,
        # 0 : l'option n'est pas proposée sur l'écran de connexion.
        "remember_me_days": settings.remember_me_days,
    }


@router.get("/me")
def me(user: User = Depends(get_authenticated_identity)):
    # Exception délibérée à `get_current_user` : le Dashboard doit pouvoir
    # afficher l'identité du compte sur l'écran de changement de mot de passe
    # imposé, donc avant que la contrainte ne soit levée.
    return {
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
    }


class UpdateProfilePayload(BaseModel):
    email: Optional[EmailStr] = None


@router.patch("/me")
def update_me(
    payload: UpdateProfilePayload,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """
    Auto-modification limitée à l'email : le nom d'utilisateur et le rôle ne
    se changent jamais soi-même (le rôle en particulier doit rester une
    décision d'un administrateur, cf. routes_users.py).
    """
    # PATCH : seul un champ explicitement transmis est modifié. Un corps vide
    # ne touche à rien ; effacer l'email demande "email": null ou "".
    if "email" in payload.model_fields_set:
        user.email = payload.email or None
    db.add(user)
    db.commit()
    return {
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
    }


class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: Password


@router.post("/change-password")
def change_password(
    payload: ChangePasswordPayload,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(get_authenticated_identity),
):
    """
    Change le mot de passe de l'utilisateur connecté. Obligatoire avant tout
    accès au Dashboard tant que `must_change_password` est vrai, c'est ce
    qui rend le compte admin/admin par défaut sûr à l'usage (façon
    SonarQube) : on ne peut pas rester dessus.
    """
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect.")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit être différent de l'actuel.")

    user.hashed_password = hash_password(payload.new_password)
    user.must_change_password = False
    db.add(user)
    admin_audit.record(db, user, "auth.password_change", target_type="user", target_id=user.id, target_label=user.username, request=request)

    return {"status": "success", "message": "Mot de passe changé avec succès."}
