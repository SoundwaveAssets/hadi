"""Lecture des payloads de push. Gitea et GitHub partagent le même format ; GitLab a le sien."""
from __future__ import annotations

from app.providers.base import PushEvent


def _actor(*candidates: dict | None, login_keys: tuple[str, ...]) -> tuple[str | None, str | None]:
    """Premier objet portant un login : (login, id en texte)."""
    for candidate in candidates:
        if not candidate:
            continue
        login = next((candidate[k] for k in login_keys if candidate.get(k)), None)
        if login:
            identifier = candidate.get("id")
            return str(login), (str(identifier) if identifier is not None else None)
    return None, None


def _files(commit: dict) -> dict:
    return {
        "added": list(commit.get("added") or []),
        "removed": list(commit.get("removed") or []),
        "modified": list(commit.get("modified") or []),
    }


def parse_github_like(payload: dict) -> PushEvent | None:
    head = payload.get("head_commit") or {}
    commits = payload.get("commits") or []
    if payload.get("deleted") or not head.get("id") or not commits:
        return None
    ref = payload.get("ref") or ""
    if not ref.startswith("refs/heads/"):
        return None
    repo = (payload.get("repository") or {}).get("name")
    if not repo:
        return None
    # `sender` est l'acteur authentifié de l'événement ; `pusher` porte le login
    # chez Gitea (login/username) et le nom de compte chez GitHub (name).
    pusher_login, pusher_id = _actor(payload.get("sender"), payload.get("pusher"), login_keys=("login", "username", "name"))
    return PushEvent(
        repository=repo,
        branch=ref.removeprefix("refs/heads/"),
        commit_id=head["id"],
        commit_message=head.get("message") or "Sans message",
        author=(head.get("author") or {}).get("name") or "Anonyme",
        commits=[_files(c) for c in commits],
        head_timestamp=head.get("timestamp"),
        pusher_login=pusher_login,
        pusher_id=pusher_id,
    )


def parse_gitlab(payload: dict) -> PushEvent | None:
    if payload.get("object_kind") != "push":
        return None
    sha = payload.get("checkout_sha")
    commits = payload.get("commits") or []
    if not sha or not commits:
        return None
    ref = payload.get("ref") or ""
    if not ref.startswith("refs/heads/"):
        return None
    repo = (payload.get("project") or {}).get("name")
    if not repo:
        return None
    head = next((c for c in commits if c.get("id") == sha), commits[-1])
    user_id = payload.get("user_id")
    return PushEvent(
        repository=repo,
        branch=ref.removeprefix("refs/heads/"),
        commit_id=sha,
        commit_message=head.get("message") or "Sans message",
        author=(head.get("author") or {}).get("name") or payload.get("user_name") or "Anonyme",
        commits=[_files(c) for c in commits],
        head_timestamp=head.get("timestamp"),
        pusher_login=payload.get("user_username") or None,
        pusher_id=str(user_id) if user_id is not None else None,
    )
