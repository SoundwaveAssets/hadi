"""Sortie : Rich pour un humain, JSON brut avec --json pour un script."""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable

from rich.console import Console
from rich.table import Table

console = Console()
state = {"json": False}

STATUS_COLORS = {
    "DEPLOYED": "green",
    "DEPLOYING": "cyan",
    "BLOCKED": "red",
    "WAITING_HUMAN": "yellow",
    "DEROGATION_PENDING": "yellow",
    "DEROGATION_REQUESTED": "yellow",
    "ANALYSIS_FAILED": "red",
    "DEPLOY_FAILED": "red",
    "PENDING": "white",
    "AUTO_AUTH": "green",
    "DEROGATION": "green",
    "REJECTED_INVALID_SIGNATURE": "red",
}

#: États définitifs : plus rien ne les fait évoluer seuls, `watch` s'arrête là.
#: Même vocabulaire que l'API (app/domain/pipeline_status.py) ; un test le vérifie.
TERMINAL_STATUSES = {"DEPLOYED", "DEPLOY_FAILED", "BLOCKED", "ANALYSIS_FAILED"}

#: En attente d'une décision humaine : `watch` s'arrête aussi, mais en le
#: disant. Continuer à sonder pendant des heures ne sert à rien, et laisser
#: un job CI bloqué là-dessus est pire : il tiendrait un agent pour rien.
AWAITING_HUMAN_STATUSES = {"WAITING_HUMAN", "DEROGATION_PENDING"}


def paint(status: str) -> str:
    color = STATUS_COLORS.get(status, "white")
    return f"[{color}]{status}[/{color}]"


def emit(data, render: Callable[[], None]) -> None:
    if state["json"]:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        render()


def table(title: str, columns: Iterable[str | tuple[str, dict]], rows: Iterable[Iterable[str]]) -> Table:
    """Une colonne : son titre, ou (titre, options Rich) pour la justification et le style."""
    t = Table(title=title)
    for column in columns:
        name, options = (column, {}) if isinstance(column, str) else column
        t.add_column(name, **options)
    for row in rows:
        t.add_row(*row)
    return t


def when(iso_timestamp: str) -> str:
    return iso_timestamp[:16].replace("T", " ")
