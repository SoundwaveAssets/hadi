"""
Les trois forges derrière le contrat VersionControlProvider. Gitea n'a pas
de SDK Python maintenu : client httpx minimal. GitHub et GitLab passent par
PyGithub et python-gitlab (synchrones, donc exécutés dans un thread).
"""
from __future__ import annotations

import asyncio
import base64
import hmac
from collections.abc import Mapping

import gitlab
import httpx
from github import Auth, Github, GithubException

from app.core.security import verify_hmac_signature
from app.core.tls import context_for
from app.providers._push import parse_github_like, parse_gitlab
from app.providers.base import PushEvent

_TIMEOUT = 15


def _header(headers: Mapping[str, str], name: str) -> str:
    # Starlette normalise en minuscules, un dict de test pas forcément.
    return headers.get(name) or headers.get(name.lower()) or ""


class GiteaProvider:
    kind = "gitea"

    def __init__(self, url: str, token: str):
        self.api_url = url.rstrip("/") + "/api/v1"
        self.headers = {"Authorization": f"token {token}"}

    @staticmethod
    def repository_name(payload: dict) -> str | None:
        return (payload.get("repository") or {}).get("name")

    @staticmethod
    def verify_signature(raw_body: bytes, headers: Mapping[str, str], secret: str) -> bool:
        signature = _header(headers, "X-Gitea-Signature") or _header(headers, "X-Hub-Signature-256")
        return verify_hmac_signature(raw_body, secret, signature)

    @staticmethod
    def delivery_id(headers: Mapping[str, str]) -> str | None:
        return _header(headers, "X-Gitea-Delivery") or None

    @staticmethod
    def parse_push(payload: dict) -> PushEvent | None:
        return parse_github_like(payload)

    async def get_file(self, owner: str, repo: str, path: str, ref: str) -> dict:
        url = f"{self.api_url}/repos/{owner}/{repo}/contents/{path}"
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True, verify=context_for(self.api_url)) as client:
            response = await client.get(url, params={"ref": ref}, headers=self.headers)
        if response.status_code != 200:
            raise RuntimeError(f"Gitea : lecture de {owner}/{repo}:{path}@{ref} refusée (HTTP {response.status_code}) : {response.text[:200]}")
        data = response.json()
        if data.get("encoding") != "base64" or data.get("content") is None:
            raise RuntimeError(f"Gitea : {path} n'est pas un fichier lisible ({data.get('type')}).")
        return {"content": base64.b64decode(data["content"]).decode("utf-8"), "sha": data["sha"]}

    async def update_file(self, owner: str, repo: str, path: str, branch: str, content: str, sha: str, message: str) -> str:
        url = f"{self.api_url}/repos/{owner}/{repo}/contents/{path}"
        payload = {"branch": branch, "sha": sha, "message": message, "content": base64.b64encode(content.encode("utf-8")).decode("ascii")}
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True, verify=context_for(self.api_url)) as client:
            response = await client.put(url, json=payload, headers=self.headers)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Gitea : écriture de {owner}/{repo}:{path}@{branch} refusée (HTTP {response.status_code}) : {response.text[:200]}")
        commit_sha = (response.json().get("commit") or {}).get("sha")
        if not commit_sha:
            raise RuntimeError("Gitea : réponse sans SHA de commit.")
        return commit_sha

    async def test_connection(self) -> dict:
        base = self.api_url
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, verify=context_for(self.api_url)) as client:
            version = await client.get(f"{base}/version")
            try:
                ok = version.status_code == 200 and "version" in version.json()
            except ValueError:
                ok = False
            if not ok:
                return {"reachable": False, "code": "unexpected", "http": version.status_code, "message": "Un serveur répond mais ne ressemble pas à Gitea."}
            if not self.headers.get("Authorization", "").removeprefix("token "):
                return {"reachable": True, "code": "no_auth", "message": "Joignable, sans identifiants."}
            response = await client.get(f"{base}/user", headers=self.headers)
        return auth_result(response.status_code)


class GitHubProvider:
    """`url` est la base de l'API : vide = https://api.github.com, ou https://<ghe>/api/v3."""

    kind = "github"

    def __init__(self, url: str, token: str):
        self.api_url = (url or "https://api.github.com").rstrip("/")
        self.token = token
        self.client = Github(auth=Auth.Token(token) if token else None, base_url=self.api_url, timeout=_TIMEOUT)

    @staticmethod
    def repository_name(payload: dict) -> str | None:
        return (payload.get("repository") or {}).get("name")

    @staticmethod
    def verify_signature(raw_body: bytes, headers: Mapping[str, str], secret: str) -> bool:
        return verify_hmac_signature(raw_body, secret, _header(headers, "X-Hub-Signature-256"))

    @staticmethod
    def delivery_id(headers: Mapping[str, str]) -> str | None:
        return _header(headers, "X-GitHub-Delivery") or None

    @staticmethod
    def parse_push(payload: dict) -> PushEvent | None:
        return parse_github_like(payload)

    async def get_file(self, owner: str, repo: str, path: str, ref: str) -> dict:
        def _get() -> dict:
            content = self.client.get_repo(f"{owner}/{repo}").get_contents(path, ref=ref)
            if isinstance(content, list):
                raise RuntimeError(f"GitHub : {path} est un dossier.")
            return {"content": content.decoded_content.decode("utf-8"), "sha": content.sha}

        try:
            return await asyncio.to_thread(_get)
        except GithubException as e:
            raise RuntimeError(f"GitHub : lecture de {owner}/{repo}:{path}@{ref} refusée (HTTP {e.status}) : {e.data}") from e

    async def update_file(self, owner: str, repo: str, path: str, branch: str, content: str, sha: str, message: str) -> str:
        def _put() -> str:
            result = self.client.get_repo(f"{owner}/{repo}").update_file(path, message, content, sha, branch=branch)
            return result["commit"].sha

        try:
            return await asyncio.to_thread(_put)
        except GithubException as e:
            raise RuntimeError(f"GitHub : écriture de {owner}/{repo}:{path}@{branch} refusée (HTTP {e.status}) : {e.data}") from e

    async def test_connection(self) -> dict:
        def _probe() -> dict:
            if not self.token:
                self.client.get_rate_limit()
                return {"reachable": True, "code": "no_auth", "message": "Joignable, sans identifiants."}
            _ = self.client.get_user().login
            return {"reachable": True, "code": "auth_ok", "message": "Joignable, identifiants acceptés."}

        try:
            return await asyncio.to_thread(_probe)
        except GithubException as e:
            return auth_result(e.status)


class GitLabProvider:
    """`url` est l'instance : vide = https://gitlab.com."""

    kind = "gitlab"

    def __init__(self, url: str, token: str):
        self.base_url = (url or "https://gitlab.com").rstrip("/")
        self.token = token
        self.client = gitlab.Gitlab(self.base_url, private_token=token or None, timeout=_TIMEOUT)

    @staticmethod
    def repository_name(payload: dict) -> str | None:
        return (payload.get("project") or {}).get("name")

    @staticmethod
    def verify_signature(raw_body: bytes, headers: Mapping[str, str], secret: str) -> bool:
        # GitLab n'envoie pas de HMAC : le secret est transmis tel quel dans
        # X-Gitlab-Token. Comparaison à temps constant, rien d'autre à faire.
        received = _header(headers, "X-Gitlab-Token")
        return bool(received and secret) and hmac.compare_digest(received.encode(), secret.encode())

    @staticmethod
    def delivery_id(headers: Mapping[str, str]) -> str | None:
        return _header(headers, "X-Gitlab-Event-UUID") or None

    @staticmethod
    def parse_push(payload: dict) -> PushEvent | None:
        return parse_gitlab(payload)

    async def get_file(self, owner: str, repo: str, path: str, ref: str) -> dict:
        def _get() -> dict:
            f = self.client.projects.get(f"{owner}/{repo}", lazy=True).files.get(file_path=path, ref=ref)
            # last_commit_id joue le rôle du sha de version : renvoyé à
            # l'écriture pour refuser un PUT sur une version périmée.
            return {"content": f.decode().decode("utf-8"), "sha": f.last_commit_id}

        try:
            return await asyncio.to_thread(_get)
        except gitlab.GitlabError as e:
            raise RuntimeError(f"GitLab : lecture de {owner}/{repo}:{path}@{ref} refusée (HTTP {e.response_code}) : {e.error_message}") from e

    async def update_file(self, owner: str, repo: str, path: str, branch: str, content: str, sha: str, message: str) -> str:
        def _put() -> str:
            project = self.client.projects.get(f"{owner}/{repo}", lazy=True)
            project.files.update(
                file_path=path,
                new_data={
                    "branch": branch,
                    "commit_message": message,
                    "encoding": "base64",
                    "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                    "last_commit_id": sha,
                },
            )
            # La réponse ne contient pas le commit créé : on relit la branche.
            return project.branches.get(branch).commit["id"]

        try:
            return await asyncio.to_thread(_put)
        except gitlab.GitlabError as e:
            raise RuntimeError(f"GitLab : écriture de {owner}/{repo}:{path}@{branch} refusée (HTTP {e.response_code}) : {e.error_message}") from e

    async def test_connection(self) -> dict:
        def _probe() -> dict:
            if not self.token:
                # /version exige un jeton : un 401 prouve quand même que c'est GitLab.
                try:
                    self.client.version()
                except gitlab.GitlabAuthenticationError:
                    return {"reachable": True, "code": "auth_required", "message": "Joignable, authentification requise."}
                return {"reachable": True, "code": "no_auth", "message": "Joignable, sans identifiants."}
            self.client.auth()
            return {"reachable": True, "code": "auth_ok", "message": "Joignable, identifiants acceptés."}

        try:
            return await asyncio.to_thread(_probe)
        except gitlab.GitlabError as e:
            return auth_result(e.response_code or 0)


def auth_result(status: int, *, authenticated: bool = True) -> dict:
    """Résultat d'un test de connexion, même forme pour toutes les intégrations."""
    if status == 200:
        if authenticated:
            return {"reachable": True, "code": "auth_ok", "message": "Joignable, identifiants acceptés."}
        return {"reachable": True, "code": "no_auth", "message": "Joignable, sans identifiants."}
    if status in (401, 403):
        return {"reachable": True, "code": "auth_refused", "http": status, "message": f"Joignable, identifiants refusés (HTTP {status})."}
    return {"reachable": False, "code": "unexpected", "http": status, "message": f"Réponse inattendue (HTTP {status})."}
