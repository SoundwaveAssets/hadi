"""File d'attente, validations à quatre yeux, dérogations, journal d'audit."""
from __future__ import annotations

from typing import Optional

import typer

from hadi import client
from hadi.output import console, emit, paint, table, when


def register(app: typer.Typer) -> None:
    @app.command()
    def pending(repository: Optional[str] = typer.Option(None, "--repo", "-r")):
        """Pipelines qui attendent une action d'un administrateur."""
        entries = client.get("/decisions/pending", params={"repository": repository} if repository else {})

        def render():
            if not entries:
                console.print("[bold green]Rien en attente.[/bold green]")
                return
            columns = [("ID", {"justify": "right", "style": "cyan"}), ("Dépôt", {"style": "magenta"}), ("Développeur", {"style": "blue"}), "Décision", ("Score IA", {"justify": "right"}), ("Vulnérabilités", {"justify": "right"})]

            def row(e):
                score = e.get("ai_anomaly_score") or 0.0
                return [str(e["id"]), e["repository_name"], e["developer_username"], paint(e["decision"]), f"[{'red' if score > 0.7 else 'yellow'}]{score}[/]", str(e.get("sonarqube_vulnerabilities"))]

            console.print(table("En attente d'action", columns, map(row, entries)))

        emit(entries, render)

    @app.command()
    def approve(
        audit_id: int = typer.Argument(..., help="ID de l'entrée d'audit"),
        justification: str = typer.Option(..., "--justification", "-j", help="Justification écrite"),
    ):
        """Valide un pipeline bloqué ou en attente (deux validateurs distincts requis)."""
        data = client.post(f"/decisions/{audit_id}/approve", json={"justification": justification})
        color = "green" if data.get("status") == "success" else "yellow"
        console.print(f"[bold {color}]{data.get('message', 'Validation enregistrée.')}[/bold {color}]")

    @app.command(name="request-derogation")
    def request_derogation(
        audit_id: int = typer.Argument(..., help="ID de l'entrée d'audit"),
        justification: str = typer.Option(..., "--justification", "-j", help="Motif"),
    ):
        """Demande une dérogation sur l'un de vos pipelines bloqués ou en attente."""
        client.post(f"/decisions/{audit_id}/request-derogation", json={"justification": justification})
        console.print("[bold green]Demande enregistrée, un administrateur va l'examiner.[/bold green]")

    @app.command()
    def derogations():
        """Dérogations accordées."""
        entries = client.get("/decisions/derogations")

        def render():
            if not entries:
                console.print("[dim]Aucune dérogation.[/dim]")
                return
            columns = [("ID", {"justify": "right", "style": "cyan"}), "Date", ("Dépôt", {"style": "magenta"}), ("Commit", {"style": "dim"}), "Validations", ("Justification", {"max_width": 60})]
            rows = ([str(e["id"]), when(e["timestamp"]), e["repository_name"], e["commit_hash"][:8], f"{e.get('approved_by')} / {e.get('four_eyes_approved_by')}", e["justification"]] for e in entries)
            console.print(table("Dérogations", columns, rows))

        emit(entries, render)

    @app.command()
    def audit(
        limit: int = typer.Option(25, "--limit", "-n"),
        repository: Optional[str] = typer.Option(None, "--repo", "-r"),
        decision: Optional[str] = typer.Option(None, "--decision", "-d"),
    ):
        """Dernières entrées du journal d'audit."""
        params = {"limit": limit, "repository": repository, "decision": decision}
        data = client.get("/audit", params={k: v for k, v in params.items() if v is not None})

        def render():
            columns = [("ID", {"justify": "right", "style": "cyan"}), "Date", ("Dépôt", {"style": "magenta"}), ("Développeur", {"style": "blue"}), ("Commit", {"style": "dim"}), "Décision"]
            rows = ([str(e["id"]), when(e["timestamp"]), e["repository_name"], e["developer_username"], e["commit_hash"][:8], paint(e["decision"])] for e in data["entries"])
            console.print(table(f"Journal d'audit · {data['total']} entrées", columns, rows))

        emit(data, render)

    @app.command(name="admin-events")
    def admin_events(
        limit: int = typer.Option(25, "--limit", "-n"),
        actor: Optional[str] = typer.Option(None, "--actor", "-a"),
        action: Optional[str] = typer.Option(None, "--action", help="Préfixe : user., auth., integration., pipeline., policy., module."),
    ):
        """Dernières actions d'administration (comptes, intégrations, modules, politiques, connexions)."""
        params = {"limit": limit, "actor": actor, "action": action}
        data = client.get("/audit/admin-events", params={k: v for k, v in params.items() if v is not None})

        def render():
            columns = [("ID", {"justify": "right", "style": "cyan"}), "Date", ("Acteur", {"style": "blue"}), "Action", ("Cible", {"style": "magenta"}), ("IP", {"style": "dim"})]
            rows = ([str(e["id"]), when(e["timestamp"]), e["actor"], e["action"], f"{e['target_type']} {e.get('target_label') or e.get('target_id') or ''}".strip(), e.get("ip") or ""] for e in data["entries"])
            console.print(table(f"Actions d'administration · {data['total']} événements", columns, rows))

        emit(data, render)

    @app.command(name="audit-verify")
    def audit_verify():
        """Rejoue les deux chaînes d'intégrité (décisions, actions d'administration). Code de sortie 1 si l'une est rompue."""
        broken = False
        for path, label in (("/audit/verify", "Journal des décisions"), ("/audit/admin-events/verify", "Journal des actions d'administration")):
            data = client.get(path)
            if data["status"] == "intact":
                console.print(f"[bold green]{label} intact.[/bold green]")
            else:
                console.print(f"[bold red]{label} : {data['message']}[/bold red]")
                broken = True
        if broken:
            raise typer.Exit(code=1)
