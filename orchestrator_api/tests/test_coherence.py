"""
Garde-fous contre les dérives silencieuses.

Un audit est une photo ; ces contrôles, eux, tournent à chaque exécution.
Chacun correspond à une incohérence réellement trouvée dans ce dépôt :
code que plus rien n'appelle, route qu'aucun client n'atteint, clé de
traduction orpheline, réglage livré sans interface pour le régler.
"""
import ast
import re
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1]
RACINE = API.parent
FRONTEND = RACINE / "frontend"
CLI = RACINE / "cli"


def lire(dossier: Path, motif: str) -> str:
    return "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in dossier.rglob(motif)
        if "node_modules" not in str(p) and ".next" not in str(p) and "__pycache__" not in str(p)
    )


@pytest.fixture(scope="module")
def sources_python() -> str:
    return lire(API / "app", "*.py") + lire(API / "tests", "*.py") + lire(CLI, "*.py")


def test_aucune_fonction_publique_orpheline(sources_python):
    """
    Une fonction publique que personne n'appelle est soit un oubli de
    suppression, soit une fonctionnalité jamais branchée. Les deux méritent
    d'être vues : `generate_webhook_secret` a vécu des mois en promettant
    dans sa docstring un usage dans l'interface qui n'existait pas.
    """
    orphelines = []
    for fichier in (API / "app").rglob("*.py"):
        if "__pycache__" in str(fichier):
            continue
        for noeud in ast.parse(fichier.read_text(encoding="utf-8")).body:
            if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) or noeud.name.startswith("_"):
                continue
            # Une route, un middleware ou une tâche de la file n'est jamais
            # appelée par son nom : c'est son décorateur qui l'enregistre.
            if noeud.decorator_list:
                continue
            if sources_python.count(noeud.name) <= 1:
                orphelines.append(f"{fichier.relative_to(RACINE)}:{noeud.lineno} {noeud.name}()")
    assert not orphelines, "fonctions publiques jamais référencées : " + ", ".join(orphelines)


@pytest.mark.skipif(not FRONTEND.exists(), reason="interface absente (image API seule)")
def test_aucune_route_de_l_api_n_est_injoignable():
    """
    Une route que ni l'interface ni la CLI n'appellent est une fonctionnalité
    livrée à moitié : le critère de sécurité a existé un temps sans aucun
    moyen de le régler autrement qu'en forgeant une requête à la main.
    """
    from app.main import app

    clients = lire(FRONTEND / "lib", "*.ts") + lire(FRONTEND / "app", "*.tsx") + lire(CLI / "hadi", "*.py")
    orphelines = []
    for route in app.routes:
        chemin = getattr(route, "path", "")
        if not chemin.startswith("/api") or chemin == "/api/health":
            continue
        fragment = re.sub(r"\{[^}]+\}", "", chemin).rstrip("/").replace("/api", "", 1)
        if fragment and fragment not in clients:
            orphelines.append(f"{sorted(route.methods)} {chemin}")
    assert not orphelines, "routes qu'aucun client n'appelle : " + ", ".join(orphelines)


@pytest.mark.skipif(not FRONTEND.exists(), reason="interface absente")
def test_aucune_cle_de_traduction_orpheline():
    """Trente-deux clés mortes traînaient dans les deux dictionnaires."""
    i18n = FRONTEND / "lib" / "i18n"
    declarees = set(re.findall(r'^\s*"([\w.]+)":', (i18n / "fr.ts").read_text(encoding="utf-8"), re.M))

    utilisation = "\n".join(
        p.read_text(encoding="utf-8")
        for p in list(FRONTEND.rglob("*.tsx")) + list(FRONTEND.rglob("*.ts"))
        if "node_modules" not in str(p) and ".next" not in str(p) and "i18n" not in str(p)
    )
    citees = set(re.findall(r'["`]([\w.]+)["`]', utilisation))
    # Clés construites dynamiquement : t(`role.${user.role}`), t(`audit.action.${x}`)...
    prefixes = tuple(re.findall(r"`([\w.]+?)\.?\$\{", utilisation))

    orphelines = sorted(k for k in declarees if k not in citees and not k.startswith(prefixes))
    assert not orphelines, f"clés jamais utilisées : {orphelines}"


@pytest.mark.skipif(not FRONTEND.exists(), reason="interface absente")
def test_chaque_page_du_tableau_de_bord_est_atteignable():
    """Une page sans lien est une page qui n'existe pas pour l'utilisateur."""
    layout = (FRONTEND / "app" / "dashboard" / "layout.tsx").read_text(encoding="utf-8")
    # Les entrées de navigation sont des objets (href: "…"), le menu du
    # compte des attributs JSX (href="…") : les deux formes comptent.
    liens = set(re.findall(r'href[=:]\s*"(/dashboard[^"]*)"', layout))
    pages = {
        "/dashboard/" + p.parent.name
        for p in (FRONTEND / "app" / "dashboard").glob("*/page.tsx")
        if not p.parent.name.startswith("[")
    }
    assert pages <= liens, f"pages sans lien dans la navigation : {sorted(pages - liens)}"


@pytest.mark.skipif(not FRONTEND.exists(), reason="interface absente")
def test_aucun_hook_d_api_orphelin():
    """
    Un hook exporté que rien n'appelle, c'est une fonctionnalité livrée à
    moitié : `useRetrigger` a existé des semaines avec sa route côté API et
    sa commande côté CLI, mais aucun bouton dans l'interface. Personne ne
    pouvait relancer un pipeline depuis le tableau de bord.
    """
    api = FRONTEND / "lib" / "api"
    déclarés = set()
    for fichier in api.glob("*.ts"):
        if fichier.name == "index.ts":
            continue
        déclarés |= set(re.findall(r"export const (use[A-Z]\w+)", fichier.read_text(encoding="utf-8")))

    consommateurs = "\n".join(
        p.read_text(encoding="utf-8")
        for p in list((FRONTEND / "app").rglob("*.tsx")) + list((FRONTEND / "components").rglob("*.tsx")) + list((FRONTEND / "contexts").rglob("*.tsx"))
    )
    orphelins = sorted(h for h in déclarés if h not in consommateurs)
    assert not orphelins, f"hooks exportés qu'aucune page n'utilise : {orphelins}"
