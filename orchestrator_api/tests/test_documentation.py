"""
Le README est la documentation de référence : ce qu'il décrit doit exister,
et ce que le code expose doit y figurer.
"""
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent.parent
README = (RACINE / "README.md").read_text(encoding="utf-8")


def test_toutes_les_routes_de_l_api_sont_documentees():
    from app.main import app

    absentes = [
        chemin
        for r in app.routes
        if (chemin := getattr(r, "path", "")).startswith("/api")
        and chemin.replace("/api", "", 1) not in README
    ]
    assert not absentes, f"routes absentes du README : {absentes}"


def test_toutes_les_variables_d_environnement_sont_documentees():
    from app.config import Settings

    absentes = [f.alias for f in Settings.model_fields.values() if f.alias and f.alias not in README]
    assert not absentes, f"variables absentes du README : {absentes}"


def test_tous_les_statuts_sont_documentes():
    from app.domain.pipeline_status import PipelineStatus

    absents = [s.value for s in PipelineStatus if s.value not in README]
    assert not absents, f"statuts absents du README : {absents}"


def test_tous_les_modules_sont_documentes():
    from app.modules.registry import MODULES

    absents = [m.name for m in MODULES if m.name not in README]
    assert not absents, f"modules absents du README : {absents}"


def test_tous_les_criteres_de_securite_sont_documentes():
    from app.domain.decision import SecurityCriterion

    absents = [c.value for c in SecurityCriterion if c.value not in README]
    assert not absents, f"critères absents du README : {absents}"


def test_aucun_fichier_reference_n_est_absent():
    cibles = {f for f in re.findall(r"\]\((?!https?:|#)([^)#]+)", README)}
    absents = sorted(f for f in cibles if not (RACINE / f).exists())
    assert not absents, f"fichiers référencés mais absents : {absents}"


def test_aucune_ancre_cassee():
    def slug(titre: str) -> str:
        s = titre.strip().lower().replace("'", "").replace("’", "")
        s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
        return re.sub(r"\s+", "-", s).strip("-")

    ancres = {slug(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+)$", README, re.M)}
    cassees = sorted({a for a in re.findall(r"\]\(#([^)]+)\)", README) if a not in ancres})
    assert not cassees, f"ancres cassées : {cassees}"


@pytest.mark.parametrize("fichier", ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "NOTICE"])
def test_aucun_tiret_cadratin(fichier: str):
    assert "—" not in (RACINE / fichier).read_text(encoding="utf-8")


def test_une_seule_mention_de_l_assistant_et_a_sa_place():
    lignes = [i for i, ligne in enumerate(README.splitlines(), 1) if "claude" in ligne.lower()]
    assert len(lignes) == 1, f"mentions attendues sur une seule ligne, trouvées aux lignes {lignes}"
    assert "Outils de développement" in README


def test_toutes_les_commandes_de_la_cli_sont_documentees():
    noms: set[str] = set()
    for fichier in (RACINE / "cli" / "hadi").rglob("*.py"):
        source = fichier.read_text(encoding="utf-8")
        for m in re.finditer(r"@app\.command\((?:name=\"([\w-]+)\")?\)\s*\n\s*def (\w+)", source):
            noms.add(m.group(1) or m.group(2).replace("_", "-"))
    absentes = sorted(n for n in noms if f"`{n}`" not in README and f"hadi {n}" not in README)
    assert not absentes, f"commandes CLI absentes du README : {absentes}"


def test_le_port_publie_est_le_meme_partout():
    compose = (RACINE / "docker-compose.yml").read_text(encoding="utf-8")
    port = re.search(r"\$\{PUBLIC_PORT:-(\d+)\}", compose).group(1)
    for fichier in ("Makefile", "README.md", "CONTRIBUTING.md", ".github/workflows/ci.yml", "frontend/package.json"):
        contenu = (RACINE / fichier).read_text(encoding="utf-8")
        assert port in contenu, f"{fichier} ne mentionne pas le port publié {port}"


def test_la_version_du_changelog_existe_dans_les_projets():
    changelog = (RACINE / "CHANGELOG.md").read_text(encoding="utf-8")
    version = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M).group(1)
    for fichier in ("cli/pyproject.toml", "frontend/package.json", "cli/hadi/__init__.py"):
        assert version in (RACINE / fichier).read_text(encoding="utf-8"), f"{fichier} n'est pas en version {version}"


def test_aucune_version_inventee_dans_la_documentation():
    """Une version citée en exemple doit exister : sinon la commande échoue chez le lecteur."""
    publiees = set(re.findall(r"^## \[(\d+\.\d+\.\d+)\]", (RACINE / "CHANGELOG.md").read_text(encoding="utf-8"), re.M))
    citees = set(re.findall(r"HADI_VERSION=(\d[\w.]*)", README))
    assert citees <= publiees, f"versions citées mais jamais publiées : {sorted(citees - publiees)}"


def test_la_feuille_de_route_ne_contredit_pas_l_installation():
    """
    « Images multi-architecture publiées » a été coché pendant que la section
    Démarrage prévenait que les images sont en `amd64` : le lecteur d'une
    machine ARM lisait l'inverse selon la section ouverte.
    """
    amd64_seul = "Les images publiées sont en `amd64`" in README
    multi_architecture_coche = "- [x] Images multi-architecture publiées" in README
    assert not (amd64_seul and multi_architecture_coche)
