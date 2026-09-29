from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.crypto import secret_box
from app.core.database import get_session
from app.core.deps import require_module, require_roles
from app.models.notification_config import NotificationConfig
from app.models.user import User, UserRole
from app.services import admin_audit
from app.services.notifier import send_email

router = APIRouter(dependencies=[Depends(require_module("notifications"))])

_SECRET_FIELDS = {"smtp_password"}


def _to_masked_dict(config: NotificationConfig) -> dict:
    data = config.model_dump()
    for field in _SECRET_FIELDS:
        data[field] = bool(data.get(field))
    return data


@router.get("/config")
def get_notification_config(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    config = db.exec(select(NotificationConfig).where(NotificationConfig.id == 1)).first()
    if not config:
        return {}
    return _to_masked_dict(config)


@router.post("/config")
def save_notification_config(
    config_data: NotificationConfig,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    existing = db.exec(select(NotificationConfig).where(NotificationConfig.id == 1)).first()
    payload = config_data.model_dump(exclude_unset=True, exclude={"id"})
    before = {key: getattr(existing, key, None) for key in payload}

    if payload.get("smtp_password"):
        payload["smtp_password"] = secret_box.encrypt(payload["smtp_password"])
    elif "smtp_password" in payload:
        # Champ vide envoyé volontairement (formulaire masqué) : on ne l'écrase
        # pas si un mot de passe est déjà configuré (même logique que routes_config.py).
        payload.pop("smtp_password")

    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        db.add(existing)
    else:
        payload["id"] = 1
        db.add(NotificationConfig(**payload))

    before, after = admin_audit.diff(before, {key: value for key, value in payload.items() if key != "id"})
    admin_audit.record(db, user, "notifications.save", target_type="notifications", before=before, after=after, request=request)
    return {"status": "success", "message": "Configuration des notifications sauvegardée."}


class TestEmailPayload(BaseModel):
    to: str


@router.post("/test")
def send_test_email(
    payload: TestEmailPayload,
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    config = db.exec(select(NotificationConfig).where(NotificationConfig.id == 1)).first()
    if not config or not config.smtp_host or not config.from_address:
        raise HTTPException(status_code=400, detail="Configurez d'abord le serveur SMTP et l'adresse d'expédition.")
    try:
        send_email(config, [payload.to], "[Hadi] E-mail de test", "Ceci est un e-mail de test envoyé depuis Hadi.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Échec de l'envoi : {e}") from e
    return {"status": "success", "message": f"E-mail de test envoyé à {payload.to}."}
