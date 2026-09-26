"""
Qui a poussé ? Le nom d'auteur d'un commit est du texte libre (`git config
user.name`) : n'importe qui peut y écrire n'importe quoi. Ce qui vaut
identité, c'est le compte authentifié par la forge, et mieux encore ce
compte relié à un utilisateur de Hadi. Le journal d'audit scelle le résultat
de cette résolution et sa provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class IdentitySource(str, Enum):
    #: Login de forge relié à un compte Hadi : l'identité est vérifiée des deux côtés.
    MAPPED = "mapped"
    #: Login authentifié par la forge, sans compte Hadi relié.
    FORGE = "forge"
    #: Seul le nom d'auteur Git est disponible : non vérifié.
    GIT_AUTHOR = "git-author"


@dataclass(frozen=True)
class DeveloperIdentity:
    #: Ce qui est scellé dans l'audit et comparé aux comptes Hadi.
    username: str
    source: IdentitySource
    commit_author: str

    @property
    def verified(self) -> bool:
        return self.source is not IdentitySource.GIT_AUTHOR


def resolve_identity(mapped_username: str | None, pusher_login: str | None, commit_author: str) -> DeveloperIdentity:
    """Du plus sûr au moins sûr : compte relié, login de forge, nom d'auteur."""
    if mapped_username:
        return DeveloperIdentity(mapped_username, IdentitySource.MAPPED, commit_author)
    if pusher_login:
        return DeveloperIdentity(pusher_login, IdentitySource.FORGE, commit_author)
    return DeveloperIdentity(commit_author, IdentitySource.GIT_AUTHOR, commit_author)
