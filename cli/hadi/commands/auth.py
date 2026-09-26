"""Configuration, session, état de l'API."""
from __future__ import annotations

from typing import Optional

import httpx
import typer

from hadi import client, session
from hadi.output import console, emit
from hadi.session import SESSION_FILE
from hadi.settings import CONFIG_FILE, api_url, set_api_url


def register(app: typer.Typer) -> None:
    @app.command()
    def config(api: Optional[str] = typer.Option(None, "--api-url", help="URL de l'API, ex. http://hadi.exemple.org/api")):
        """Affiche ou modifie l'adresse de l'API."""
        if api:
            console.print(f"[green]API : {set_api_url(api)}[/green]")
            return
        data = {"api_url": api_url(), "config_file": str(CONFIG_FILE), "session_file": str(SESSION_FILE)}
        emit(data, lambda: console.print(f"API : [cyan]{api_url()}[/cyan]\nConfiguration : {CONFIG_FILE}\nSession : {SESSION_FILE}"))

    @app.command()
    def login(
        username: str = typer.Option(..., prompt=True),
        password: str = typer.Option(..., prompt=True, hide_input=True),
    ):
        """Ouvre une session."""
        data = client.post("/auth/login", auth=False, json={"username": username, "password": password})
        session.save(data)
        console.print(f"[bold green]Connecté : {data['username']} ({data['role']}).[/bold green]")
        if data.get("must_change_password"):
            console.print("[bold yellow]Mot de passe par défaut encore actif : changez-le depuis le tableau de bord.[/bold yellow]")

    @app.command()
    def logout():
        """Ferme la session locale."""
        session.clear()
        console.print("[green]Déconnecté.[/green]")

    @app.command()
    def whoami():
        """Compte connecté, revalidé auprès de l'API."""
        data = client.get("/auth/me")
        emit(data, lambda: console.print(f"[bold cyan]{data['username']}[/bold cyan] · rôle {data['role']}"))

    @app.command()
    def status():
        """État de l'API et de son installation."""
        try:
            response = httpx.get(f"{api_url()}/health", timeout=10)
        except httpx.ConnectError as e:
            console.print(f"[bold red]API injoignable à {api_url()}.[/bold red]")
            raise typer.Exit(code=1) from e
        if response.status_code == 503:
            found = response.json().get("detail", {})
            step = found.get("setup_step", "?") if isinstance(found, dict) else "?"
            console.print(f"[yellow]Installation non terminée (étape : {step}).[/yellow]")
            return
        if response.status_code == 200 and response.json().get("setup_complete"):
            console.print("[bold green]API en ligne et opérationnelle.[/bold green]")
            return
        console.print(f"[bold red]État inattendu ({response.status_code}).[/bold red]")
        raise typer.Exit(code=1)
