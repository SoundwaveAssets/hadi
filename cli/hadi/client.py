"""Appels à l'API : jeton de session, erreurs traduites, arrêt propre de la commande."""
from __future__ import annotations

import json

import httpx
import typer

from hadi import session
from hadi.output import console
from hadi.settings import api_url


def auth_headers(token: str | None = None) -> dict:
    token = token or session.token()
    if not token:
        console.print("[bold red]Pas de session. Lancez d'abord [cyan]hadi login[/cyan].[/bold red]")
        raise typer.Exit(code=1)
    return {"Authorization": f"Bearer {token}"}


def request(method: str, path: str, *, auth: bool = True, token: str | None = None, timeout: float = 30, **kwargs) -> httpx.Response:
    headers = auth_headers(token) if auth else {}
    try:
        response = httpx.request(method, f"{api_url()}{path}", headers=headers, timeout=timeout, **kwargs)
    except httpx.ConnectError as e:
        console.print(f"[bold red]API injoignable à {api_url()}. Est-elle démarrée ? (hadi config --api-url ...)[/bold red]")
        raise typer.Exit(code=1) from e
    if response.status_code >= 400:
        fail(response)
    return response


def get(path: str, **kwargs):
    return request("GET", path, **kwargs).json()


def post(path: str, **kwargs):
    return request("POST", path, **kwargs).json()


def detail(response: httpx.Response) -> str:
    try:
        found = response.json().get("detail", response.text)
        return json.dumps(found, ensure_ascii=False) if isinstance(found, (dict, list)) else str(found)
    except Exception:
        return response.text


def fail(response: httpx.Response) -> None:
    if response.status_code == 401:
        console.print("[bold red]Session expirée ou invalide. Reconnectez-vous avec [cyan]hadi login[/cyan].[/bold red]")
    elif response.status_code == 403:
        console.print(f"[bold red]Accès refusé : {detail(response)}[/bold red]")
    elif response.status_code == 404:
        console.print(f"[bold yellow]Introuvable : {detail(response)}[/bold yellow]")
    else:
        console.print(f"[bold red]Erreur {response.status_code} : {detail(response)}[/bold red]")
    raise typer.Exit(code=1)
