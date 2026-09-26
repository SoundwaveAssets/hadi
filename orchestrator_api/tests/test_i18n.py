"""
Les deux dictionnaires de l'interface doivent rester identiques en clés.

Une clé ajoutée en français et oubliée en anglais ne casse rien : elle
s'affiche telle quelle, `settings.security.title`, au milieu d'une phrase.
Personne ne le voit avant un utilisateur anglophone.
"""
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "i18n"
pytestmark = pytest.mark.skipif(not RACINE.exists(), reason="interface absente (image API seule)")


def cles(fichier: str) -> set[str]:
    return set(re.findall(r'^\s*"([\w.]+)":', (RACINE / fichier).read_text(encoding="utf-8"), re.M))


def test_les_deux_langues_ont_exactement_les_memes_cles():
    fr, en = cles("fr.ts"), cles("en.ts")
    assert fr - en == set(), f"absentes de en.ts : {sorted(fr - en)}"
    assert en - fr == set(), f"absentes de fr.ts : {sorted(en - fr)}"


def test_aucune_traduction_vide():
    for fichier in ("fr.ts", "en.ts"):
        vides = re.findall(r'^\s*"([\w.]+)":\s*""', (RACINE / fichier).read_text(encoding="utf-8"), re.M)
        assert not vides, f"{fichier} : traductions vides {vides}"
