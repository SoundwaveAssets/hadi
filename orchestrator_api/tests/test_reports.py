"""
Tests des exports.

Ils verrouillent trois correctifs qui ne se voient qu'à l'ouverture du fichier
par un humain, donc exactement le genre de régression qu'aucune autre partie
de la suite n'attraperait.
"""
import codecs
from datetime import date, datetime, timezone

import pytest

from app.services.reports import build_csv, date_range, safe_cell
from tests.conftest import login

# --- Injection de formules ---------------------------------------------------

@pytest.mark.parametrize("dangereux", ["=1+1", "+1", "-1", "@SUM(A1)", "=cmd|'/c calc'!A1"])
def test_une_cellule_interpretable_comme_formule_est_neutralisee(dangereux):
    """
    La justification d'une dérogation est saisie par un développeur et lue par
    la direction dans Excel. Un champ commençant par '=' s'y exécute.
    """
    neutralise = safe_cell(dangereux)
    assert neutralise.startswith("'")
    # La valeur reste intégralement lisible : on préfixe, on ne tronque pas.
    assert neutralise[1:] == dangereux


@pytest.mark.parametrize("normal", ["api-gateway", "Vulnérabilité critique", "0.42", ""])
def test_une_cellule_ordinaire_nest_pas_modifiee(normal):
    assert safe_cell(normal) == normal


def test_une_valeur_absente_devient_une_cellule_vide():
    assert safe_cell(None) == ""


# --- Encodage lisible par Excel ----------------------------------------------

def test_le_csv_porte_la_marque_utf8_attendue_par_excel():
    """Sans elle, Excel lit l'UTF-8 comme de l'ANSI : « Dépôt » → « DÃ©pÃ´t »."""
    assert build_csv(["Dépôt"], [["référentiel"]]).startswith(b"\xef\xbb\xbf")


def test_le_csv_utilise_le_point_virgule():
    """Séparateur attendu par Excel en locale francophone ; la virgule produit une seule colonne."""
    texte = build_csv(["A", "B"], [["1", "2"]]).decode("utf-8-sig")
    assert "A;B" in texte
    assert "1;2" in texte


def test_les_accents_survivent_a_un_aller_retour():
    texte = build_csv(["Dépôt"], [["référentiel-clients"]]).decode("utf-8-sig")
    assert "Dépôt" in texte
    assert "référentiel-clients" in texte


def test_une_formule_est_neutralisee_dans_le_fichier_produit():
    """Vérification de bout en bout, pas seulement de la fonction unitaire."""
    texte = build_csv(["Justification"], [["=cmd|'/c calc'!A1"]]).decode("utf-8-sig")
    assert "'=cmd" in texte
    assert not any(ligne.startswith("=") for ligne in texte.splitlines())


# --- Période par défaut ------------------------------------------------------

def test_la_periode_par_defaut_couvre_bien_trente_jours():
    """
    La version précédente annonçait 30 jours et calculait la journée en cours.
    L'écart ne se voyait pas depuis l'interface, qui envoie toujours des bornes.
    """
    start, end = date_range(None, None)
    assert 29 <= (end - start).days <= 31


def test_des_bornes_explicites_sont_respectees():
    start, end = date_range(date(2026, 1, 1), date(2026, 1, 31))
    assert start == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert end.date() == date(2026, 1, 31)
    assert end.hour == 23


# --- Routes ------------------------------------------------------------------

@pytest.mark.parametrize(
    ("path", "media_type", "magic"),
    [
        ("/api/reports/pipelines.csv", "text/csv", codecs.BOM_UTF8 + b"ID;"),
        ("/api/reports/audit.csv", "text/csv", codecs.BOM_UTF8 + b"ID;"),
        ("/api/reports/summary.pdf", "application/pdf", b"%PDF"),
    ],
)
def test_les_exports_repondent_avec_le_bon_type(client, path, media_type, magic):
    r = client.get(path, params={"from": "2026-01-01", "to": "2026-12-31"}, headers=login(client, "admin"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(media_type)
    assert "attachment; filename=" in r.headers["content-disposition"]
    assert r.content.startswith(magic)


def test_un_developpeur_ne_peut_pas_exporter(client):
    r = client.get("/api/reports/audit.csv", headers=login(client, "dev"))
    assert r.status_code == 403
