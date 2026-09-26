"""Assemblage de la CLI : options globales, installation, shell interactif, commandes."""
from __future__ import annotations

import shlex

import typer

from hadi import __version__, installer
from hadi.commands import auth, decisions, pipelines
from hadi.output import console, state
from hadi.settings import api_url

app = typer.Typer(help="hadi : client en ligne de commande de la passerelle de décision CI/CD", add_completion=True, no_args_is_help=False)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON brute, pour les scripts."),
    version: bool = typer.Option(False, "--version", help="Affiche la version et quitte."),
):
    state["json"] = json_output
    if version:
        console.print(f"hadi {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        if installer.launched_by_double_click():
            _first_run()
        else:
            console.print(ctx.get_help())


@app.command()
def install(force: bool = typer.Option(False, "--force", help="Réinstalle même si la version est identique.")):
    """Installe cet exécutable dans un dossier stable et l'ajoute au PATH."""
    installer.install(force=force)


@app.command()
def uninstall():
    """Retire l'exécutable installé et sa session locale."""
    installer.uninstall()


@app.command()
def shell():
    """Session interactive : tapez les commandes sans le préfixe hadi (exit pour quitter)."""
    console.print(f"[bold]hadi {__version__}[/bold] · API {api_url()} · [dim]help pour la liste, exit pour quitter[/dim]")
    while True:
        try:
            line = console.input("[cyan]hadi>[/cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not line:
            continue
        if line in {"exit", "quit"}:
            return
        args = shlex.split("--help" if line == "help" else line)
        if args and args[0] == "hadi":
            args = args[1:] or ["--help"]
        # Un hash de commit collé seul : c'est son historique qu'on veut voir,
        # pas une commande de ce nom. Le message d'erreur de Click, lui, ne
        # disait rien d'utile.
        if len(args) == 1 and _looks_like_commit(args[0]):
            args = ["history", args[0]]
        try:
            app(args, prog_name="hadi", standalone_mode=False)
        except (typer.Exit, SystemExit):
            pass
        except Exception as e:  # noqa: BLE001 : la boucle ne doit pas tomber sur une erreur de commande
            console.print(f"[bold red]{e}[/bold red]")
            console.print("[dim]help pour la liste des commandes.[/dim]")


def _looks_like_commit(value: str) -> bool:
    """
    Hash Git : 7 à 40 caractères hexadécimaux. Volontairement pas 64 : c'est
    la longueur d'une empreinte SHA-256 (celle du binaire, affichée sur la
    page Profil), et la coller ici ne veut pas dire « cherche ce commit ».
    """
    return 7 <= len(value) <= 40 and all(c in "0123456789abcdefABCDEF" for c in value)


def _first_run() -> None:
    """Double-clic sur l'exécutable : installation, puis on laisse la fenêtre ouverte."""
    console.print(f"[bold]hadi {__version__}[/bold]")
    try:
        installer.install()
    except typer.Exit:
        pass
    console.print()
    try:
        answer = console.input("[dim]Entrée pour fermer, ou tapez shell pour une session interactive : [/dim]").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if answer.lower() == "shell":
        shell()


for module in (auth, pipelines, decisions):
    module.register(app)
