"""
Point d'entrée des forges : `PROVIDERS` pour ce qui ne demande pas de
configuration (signature, lecture d'un push), `provider_for` pour un client
authentifié construit depuis ToolConfig.
"""
from __future__ import annotations

from sqlmodel import Session, select

from app.core.crypto import secret_box
from app.models.config import ToolConfig
from app.providers.base import PushEvent, VersionControlProvider
from app.providers.forges import GiteaProvider, GitHubProvider, GitLabProvider

PROVIDERS: dict[str, type] = {
    GiteaProvider.kind: GiteaProvider,
    GitHubProvider.kind: GitHubProvider,
    GitLabProvider.kind: GitLabProvider,
}
DEFAULT_PROVIDER = GiteaProvider.kind

__all__ = ["PROVIDERS", "DEFAULT_PROVIDER", "PushEvent", "VersionControlProvider", "provider_for", "provider_from_fields"]


def provider_from_fields(kind: str, url: str | None, token: str | None) -> VersionControlProvider:
    cls = PROVIDERS.get(kind)
    if cls is None:
        raise ValueError(f"Forge inconnue : {kind}")
    return cls(url or "", token or "")


def provider_for(session: Session, kind: str) -> VersionControlProvider:
    """Client authentifié pour la forge `kind`. ValueError si elle n'est pas configurée."""
    cls = PROVIDERS.get(kind)
    if cls is None:
        raise ValueError(f"Forge inconnue : {kind}")
    config = session.exec(select(ToolConfig)).first()
    url = getattr(config, f"{kind}_url", None) if config else None
    raw_token = getattr(config, f"{kind}_token", None) if config else None
    # GitHub et GitLab ont une URL publique par défaut ; Gitea est toujours auto-hébergé.
    if not raw_token or (kind == "gitea" and not url):
        raise ValueError(f"La configuration de {cls.__name__.removesuffix('Provider')} est manquante.")
    return cls(url or "", secret_box.decrypt(raw_token))
