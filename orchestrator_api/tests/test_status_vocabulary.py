"""
Un seul vocabulaire de statuts pour trois langages.

`ANALYSIS_TRIGGER_FAILED` a existé des mois dans l'interface et dans la CLI
sans qu'aucun code de l'API ne le pose jamais : personne ne pouvait le voir,
et rien ne l'aurait signalé. Ce test compare les listes à chaque exécution.
"""
import re
from pathlib import Path

import pytest

from app.domain.pipeline_status import AWAITING_HUMAN_STATUSES, TERMINAL_STATUSES, PipelineStatus

RACINE = Path(__file__).resolve().parents[2]
FRONTEND = RACINE / "frontend" / "lib" / "api" / "decisions.ts"
CLI = RACINE / "cli" / "hadi" / "output.py"


def ensemble(fichier: Path, nom: str) -> set[str]:
    """Lit un littéral `NOM = {...}` / `new Set([...])` et en extrait les chaînes."""
    contenu = fichier.read_text(encoding="utf-8")
    bloc = re.search(rf"{nom}\s*(?::[^=]+)?=\s*(?:new Set\()?[\[{{](.*?)[\]}}]", contenu, re.S)
    assert bloc, f"{nom} introuvable dans {fichier.name}"
    return set(re.findall(r'"([A-Z_]+)"', bloc.group(1)))


@pytest.mark.skipif(not FRONTEND.exists(), reason="interface absente (image API seule)")
def test_les_etats_definitifs_de_l_interface_sont_ceux_de_l_api():
    assert ensemble(FRONTEND, "TERMINAL_STATUSES") == set(TERMINAL_STATUSES)


@pytest.mark.skipif(not FRONTEND.exists(), reason="interface absente")
def test_les_attentes_humaines_de_l_interface_sont_celles_de_l_api():
    assert ensemble(FRONTEND, "AWAITING_HUMAN_STATUSES") == set(AWAITING_HUMAN_STATUSES)


@pytest.mark.skipif(not CLI.exists(), reason="CLI absente")
def test_les_etats_definitifs_de_la_cli_sont_ceux_de_l_api():
    assert ensemble(CLI, "TERMINAL_STATUSES") == set(TERMINAL_STATUSES)


def test_aucun_statut_n_est_orphelin():
    """Tout statut déclaré appartient à exactement une catégorie : définitif, attente humaine, ou travail en cours."""
    from app.domain.pipeline_status import IN_PROGRESS_STATUSES

    toutes = {s.value for s in PipelineStatus}
    catégories = [set(TERMINAL_STATUSES), set(AWAITING_HUMAN_STATUSES), set(IN_PROGRESS_STATUSES)]
    assert set().union(*catégories) == toutes
    assert sum(len(c) for c in catégories) == len(toutes)  # aucune valeur dans deux catégories
