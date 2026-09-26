"""Résolution de l'identité d'un push : lecture de la correspondance forge → compte, règle dans domain/identity.py."""
from __future__ import annotations

from sqlalchemy import or_
from sqlmodel import Session, select

from app.domain.identity import DeveloperIdentity, resolve_identity
from app.models.forge_identity import ForgeIdentity
from app.models.user import User
from app.providers.base import PushEvent


def mapped_username(db: Session, provider: str, login: str | None, external_id: str | None) -> str | None:
    """Compte Hadi relié à ce login de forge (ou à son identifiant numérique), s'il existe et est actif."""
    if not login and not external_id:
        return None
    conditions = []
    if login:
        conditions.append(ForgeIdentity.login == login)
    if external_id:
        conditions.append(ForgeIdentity.external_id == external_id)
    row = db.exec(
        select(User.username)
        .join(ForgeIdentity, ForgeIdentity.user_id == User.id)  # type: ignore[arg-type]
        .where(ForgeIdentity.provider == provider, or_(*conditions), User.is_active == True)  # noqa: E712
    ).first()
    return row


def identify_pusher(db: Session, provider: str, event: PushEvent) -> DeveloperIdentity:
    return resolve_identity(mapped_username(db, provider, event.pusher_login, event.pusher_id), event.pusher_login, event.author)
