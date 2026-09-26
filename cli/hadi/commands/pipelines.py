"""Dépôts, pipelines, journaux, suivi, relance, point de contrôle CI."""
from __future__ import annotations

import time
from typing import Optional

import httpx
import typer

from hadi import client
from hadi.output import AWAITING_HUMAN_STATUSES, TERMINAL_STATUSES, console, emit, paint, table
from hadi.settings import api_url


def register(app: typer.Typer) -> None:
    @app.command()
    def repos():
        """Dépôts enregistrés."""
        rows = client.get("/decisions/repositories")

        def render():
            if not rows:
                console.print("[dim]Aucun dépôt enregistré.[/dim]")
            for r in rows:
                console.print(r["repository"])

        emit(rows, render)

    @app.command()
    def pipelines(
        repository: Optional[str] = typer.Option(None, "--repo", "-r", help="Limiter à un dépôt"),
        limit: int = typer.Option(30, "--limit", "-n"),
    ):
        """Vos pipelines (développeur) ou tous (autres rôles)."""
        params = {"limit": limit, **({"repository": repository} if repository else {})}
        rows = client.get("/decisions/pipelines", params=params)["items"]

        def render():
            if not rows:
                console.print("[dim]Aucun pipeline.[/dim]")
                return
            columns = [("ID", {"justify": "right", "style": "cyan"}), ("Dépôt", {"style": "magenta"}), "Branche", ("Commit", {"style": "dim"}), ("Auteur", {"style": "blue"}), "Statut"]
            console.print(table("Pipelines", columns, ([str(p["id"]), p["repository"], p["branch"], p["commit_id"][:8], p["author"], paint(p["status"])] for p in rows)))

        emit(rows, render)

    @app.command()
    def logs(pipeline_id: int = typer.Argument(..., help="ID du pipeline (voir hadi pipelines)")):
        """Console Jenkins et journal du workflow d'un pipeline."""
        data = client.get(f"/decisions/pipelines/{pipeline_id}/logs")

        def render():
            console.print(f"[bold]--- Console Jenkins (pipeline #{pipeline_id}) ---[/bold]")
            console.print(data.get("jenkins_console") or "[dim]Aucune console Jenkins.[/dim]")
            console.print("\n[bold]--- Journal d'exécution ---[/bold]")
            console.print(data.get("execution_log") or "[dim]Aucun journal.[/dim]")
            for note in data.get("notes", []):
                console.print(f"[dim]Note : {note}[/dim]")

        emit(data, render)

    @app.command()
    def watch(
        pipeline_id: int = typer.Argument(..., help="ID du pipeline"),
        interval: int = typer.Option(5, "--interval", "-i", help="Secondes entre deux vérifications"),
        timeout: int = typer.Option(3600, "--timeout", "-t", help="Abandon au bout de N secondes (0 = sans limite)"),
    ):
        """
        Suit un pipeline jusqu'à ce qu'il n'y ait plus rien à attendre. Code
        de sortie 0 s'il est déployé.

        S'arrête aussi sur une attente humaine (validation, dérogation) : un
        job CI n'a pas à immobiliser un agent pendant qu'un administrateur
        réfléchit, et le suivi n'avancerait plus de toute façon. Un délai
        global évite qu'un pipeline figé retienne le terminal indéfiniment.
        """
        last_status: Optional[str] = None
        deadline = time.monotonic() + timeout if timeout else None

        while True:
            row = client.get(f"/decisions/pipelines/{pipeline_id}")
            if row["status"] != last_status:
                console.print(f"[dim]{time.strftime('%H:%M:%S')}[/dim] {row['repository']} [dim]{row['commit_id'][:8]}[/dim] {paint(row['status'])}")
                last_status = row["status"]
            if row["status"] in TERMINAL_STATUSES or row["status"] in AWAITING_HUMAN_STATUSES:
                break
            if deadline and time.monotonic() >= deadline:
                console.print(f"[bold yellow]Toujours en {last_status} après {timeout} s : abandon du suivi.[/bold yellow]")
                raise typer.Exit(code=2)
            time.sleep(interval)

        if last_status in AWAITING_HUMAN_STATUSES:
            console.print("[bold yellow]En attente d'une décision humaine : le suivi s'arrête ici.[/bold yellow]")
            console.print("[dim]Un administrateur doit valider (hadi pending), puis hadi watch pour reprendre le suivi.[/dim]")
            raise typer.Exit(code=1)

        console.print("[bold green]État définitif atteint.[/bold green]")
        if last_status == "BLOCKED":
            console.print(f"[dim]hadi logs {pipeline_id} pour le détail, hadi retrigger {pipeline_id} si la cause est l'infrastructure.[/dim]")
        raise typer.Exit(code=0 if last_status == "DEPLOYED" else 1)

    @app.command()
    def retrigger(pipeline_id: int = typer.Argument(..., help="ID du pipeline à relancer")):
        """Relance l'analyse complète d'un pipeline sur le même commit."""
        data = client.post(f"/decisions/pipelines/{pipeline_id}/retrigger")
        console.print(f"[bold green]{data.get('message', 'Relance déclenchée.')}[/bold green]")
        console.print(f"[dim]hadi watch {pipeline_id} pour suivre.[/dim]")

    @app.command()
    def history(commit_hash: str = typer.Argument(..., help="Hash du commit")):
        """Toutes les décisions prises pour un commit."""
        entries = client.get(f"/decisions/history/{commit_hash}")

        def render():
            columns = [("ID", {"justify": "right", "style": "cyan"}), "Décision", ("Score IA", {"justify": "right"}), ("Vulnérabilités", {"justify": "right"}), ("Justification", {"max_width": 70})]
            rows = ([str(e["id"]), paint(e["decision"]), str(e.get("ai_anomaly_score")), str(e.get("sonarqube_vulnerabilities")), e["justification"]] for e in entries)
            console.print(table(f"Historique · {commit_hash[:12]}", columns, rows))
            for e in entries:
                if e.get("ai_explanation"):
                    console.print(f"  [dim]#{e['id']} IA : {e['ai_explanation']}[/dim]")

        emit(entries, render)

    @app.command()
    def gate(
        repository: str = typer.Argument(..., help="Nom du dépôt enregistré"),
        commit_hash: str = typer.Argument(..., help="Commit à vérifier"),
        wait: int = typer.Option(300, "--wait", "-w", help="Secondes d'attente maximum d'une décision"),
        token: Optional[str] = typer.Option(None, "--token", envvar="HADI_TOKEN", help="Jeton API (module Jetons API), sinon la session"),
    ):
        """
        Point de contrôle pour un job CI : code de sortie 0 si le déploiement est
        autorisé, 1 sinon. Remplace le curl du Jenkinsfile généré.
        """
        try:
            response = httpx.get(
                f"{api_url()}/decisions/gate/{repository}/{commit_hash}",
                params={"wait": wait}, headers=client.auth_headers(token), timeout=wait + 30,
            )
        except httpx.ConnectError as e:
            console.print(f"[bold red]API injoignable à {api_url()}.[/bold red]")
            raise typer.Exit(code=1) from e
        if response.status_code == 200:
            console.print(f"[bold green]Autorisé : {response.json().get('decision')}[/bold green]")
            raise typer.Exit(code=0)
        console.print(f"[bold red]Refusé ou indisponible ({response.status_code}) : {client.detail(response)}[/bold red]")
        raise typer.Exit(code=1)
