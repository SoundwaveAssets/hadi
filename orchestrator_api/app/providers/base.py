"""
Contrat commun aux forges (Gitea, GitHub, GitLab). Trois responsabilités,
et rien d'autre : authentifier un webhook, lire un push, écrire un fichier
(l'écriture GitOps du déploiement). Le moteur de décision, les flows et le
webhook ne connaissent que ce contrat.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class PushEvent:
    repository: str
    branch: str
    commit_id: str
    commit_message: str
    #: Nom d'auteur du commit : texte libre (`git config user.name`), jamais une preuve d'identité.
    author: str
    #: Chaque commit normalisé : {"added": [...], "removed": [...], "modified": [...]}.
    commits: list[dict] = field(default_factory=list)
    head_timestamp: str | None = None
    #: Compte authentifié qui a poussé, tel que la forge l'affirme (sender/pusher chez
    #: Gitea et GitHub, user_username chez GitLab). C'est lui qui vaut identité.
    pusher_login: str | None = None
    pusher_id: str | None = None


class VersionControlProvider(Protocol):
    kind: str

    @staticmethod
    def repository_name(payload: dict) -> str | None:
        """Nom du dépôt tel qu'enregistré dans PipelineConfig.repository."""

    @staticmethod
    def verify_signature(raw_body: bytes, headers: Mapping[str, str], secret: str) -> bool: ...

    @staticmethod
    def delivery_id(headers: Mapping[str, str]) -> str | None:
        """Identifiant unique de la livraison, pour refuser un rejeu."""

    @staticmethod
    def parse_push(payload: dict) -> PushEvent | None:
        """None si l'événement n'est pas un push exploitable (ping, suppression de branche, tag...)."""

    async def get_file(self, owner: str, repo: str, path: str, ref: str) -> dict:
        """{"content": str, "sha": str} ; lève si absent."""

    async def update_file(
        self, owner: str, repo: str, path: str, branch: str, content: str, sha: str, message: str
    ) -> str:
        """Commite `content` par-dessus la version `sha`. Renvoie le SHA du commit."""

    async def test_connection(self) -> dict: ...
