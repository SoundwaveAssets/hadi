from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.deps import get_current_user, require_roles
from app.models.module_state import ModuleState
from app.models.user import User, UserRole
from app.modules.registry import MODULES, MODULES_BY_KEY
from app.services import admin_audit

router = APIRouter()


@router.get("")
def list_modules(
    db: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """
    État de tous les modules (registre + activation). Accessible à tout
    utilisateur authentifié, le frontend s'en sert pour filtrer sa propre
    navigation, quel que soit le rôle (le contrôle par rôle continue de
    s'appliquer par ailleurs : voir un module actif ne donne pas accès à ses
    données, seuls les rôles habilités y accèdent).
    """
    states = {s.module_key: s for s in db.exec(select(ModuleState))}
    return [
        {
            "key": m.key,
            "name": m.name,
            "description": m.description,
            "category": m.category,
            "is_core": m.is_core,
            "is_active": states[m.key].is_active if m.key in states else m.default_active,
        }
        for m in MODULES
    ]


@router.post("/{key}/toggle")
def toggle_module(
    key: str,
    request: Request,
    db: Session = Depends(get_session),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    """
    Active ou désactive un module (bascule simple). Réservé aux
    administrateurs : ça change ce que TOUS les rôles peuvent voir/faire
    dans l'application, pas juste un réglage personnel.
    """
    definition = MODULES_BY_KEY.get(key)
    if not definition:
        raise HTTPException(status_code=404, detail="Module inconnu.")
    if definition.is_core:
        raise HTTPException(status_code=400, detail="Ce module fait partie du socle et ne peut pas être désactivé.")

    state = db.get(ModuleState, key)
    if not state:
        state = ModuleState(module_key=key, is_active=definition.default_active)

    state.is_active = not state.is_active
    state.updated_at = datetime.now(timezone.utc)
    state.updated_by = admin.username
    db.add(state)
    admin_audit.record(
        db, admin, "module.toggle", target_type="module", target_id=key, target_label=definition.name,
        before={"is_active": not state.is_active}, after={"is_active": state.is_active}, request=request,
    )

    return {"key": key, "is_active": state.is_active}
