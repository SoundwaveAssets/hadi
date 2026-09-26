"""
Enregistrement des actions d'administration (models/admin_event.py).

Une route décrit ce qu'elle change, avant et après ; ce module masque ce qui
n'a rien à faire dans un journal (jetons, mots de passe, secrets de webhook),
fige les instantanés en JSON canonique et écrit l'événement dans la même
transaction que la modification. Le journal dit qu'un secret a été
(re)défini, jamais lequel.
"""
import json
from collections.abc import Mapping
from enum import Enum
from typing import Any, Optional

from fastapi import Request
from sqlmodel import Session

from app.models.admin_event import AdminEvent, append_admin_event
from app.models.user import User

REDACTED = "***"
_SECRET_HINTS = ("token", "password", "secret")


def is_secret(field: str) -> bool:
    return any(hint in field.lower() for hint in _SECRET_HINTS)


def redact(data: Optional[Mapping[str, Any]]) -> Optional[dict]:
    if data is None:
        return None
    return {key: (REDACTED if value else None) if is_secret(key) else value for key, value in data.items()}


def snapshot(obj: Any, *fields: str) -> dict:
    return {field: getattr(obj, field) for field in fields}


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[dict, dict]:
    """
    Ne garde que ce qui change. Un secret présent dans `after` compte
    toujours comme changé : masqué, il serait sinon indiscernable de l'ancien.
    """
    keys = [key for key, value in after.items() if before.get(key) != value or (is_secret(key) and value)]
    return {key: before.get(key) for key in keys}, {key: after[key] for key in keys}


def _dump(data: Optional[Mapping[str, Any]]) -> Optional[str]:
    if data is None:
        return None
    return json.dumps(data, sort_keys=True, ensure_ascii=False, default=lambda o: o.value if isinstance(o, Enum) else str(o))


def client_ip(request: Optional[Request]) -> Optional[str]:
    # Derrière un reverse-proxy, uvicorn substitue X-Forwarded-For à l'adresse
    # de la socket quand le proxy figure dans --forwarded-allow-ips.
    return request.client.host if request is not None and request.client else None


def record(
    db: Session,
    actor: User,
    action: str,
    *,
    target_type: str,
    target_id: Any = None,
    target_label: Optional[str] = None,
    before: Optional[Mapping[str, Any]] = None,
    after: Optional[Mapping[str, Any]] = None,
    request: Optional[Request] = None,
) -> AdminEvent:
    """À appeler après le `db.add` de la modification, jamais après son `commit` : c'est lui qui valide les deux."""
    event = AdminEvent(
        actor=actor.username,
        actor_role=actor.role.value,
        action=action,
        target_type=target_type,
        target_id=None if target_id is None else str(target_id),
        target_label=target_label,
        before=_dump(redact(before)),
        after=_dump(redact(after)),
        ip=client_ip(request),
    )
    return append_admin_event(db, event)
