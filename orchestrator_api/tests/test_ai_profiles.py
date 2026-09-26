"""
Profils comportementaux : le score est une fonction pure, la persistance vit
en base (une réplique qui redémarre ne réapprend pas), et les plafonds
gardent une fenêtre glissante.
"""
import json

import pytest
from sqlmodel import Session

from app.ai.infer import MIN_HISTORY_FOR_MODEL, calculate_anomaly_score
from app.ai.store import MAX_HISTORY_PER_DEVELOPER, MAX_KNOWN_FILES_PER_DEVELOPER, Profile, ProfileStore
from app.models.developer_profile import DeveloperProfile


@pytest.fixture
def store(db):
    with Session(db) as session:
        yield ProfileStore(session)


def push(hour: float = 14, files: int = 3, commits: int = 1) -> dict:
    return {"developer": "dev", "hour_of_day": hour, "files_changed": files, "commit_count": commits, "changed_file_paths": [f"src/{i}.py" for i in range(files)]}


# --- persistance -------------------------------------------------------------------

def test_un_profil_survit_au_changement_d_instance(db, store):
    store.record_push("dev", [14.0, 3.0, 1.0, 0.0], {"src/a.py", "src/b.py"})
    # Une autre session, c'est une autre réplique de l'API : elle lit le même profil.
    with Session(db) as other:
        profile = ProfileStore(other).get_profile("dev")
    assert profile.history == [[14.0, 3.0, 1.0, 0.0]]
    assert profile.known_files == ["src/a.py", "src/b.py"]


def test_developpeur_inconnu_profil_vide(store):
    assert store.get_profile("jamais-vu") == Profile(history=[], known_files=[])


def test_les_plafonds_gardent_une_fenetre_glissante(store):
    for i in range(MAX_HISTORY_PER_DEVELOPER + 5):
        store.record_push("dev", [float(i), 1.0, 1.0, 0.0], {f"f{i}.py"})
    profile = store.get_profile("dev")
    assert len(profile.history) == MAX_HISTORY_PER_DEVELOPER
    assert profile.history[0][0] == 5.0  # les plus anciens sont sortis
    assert len(profile.known_files) <= MAX_KNOWN_FILES_PER_DEVELOPER
    assert profile.known_files[-1] == f"f{MAX_HISTORY_PER_DEVELOPER + 4}.py"


def test_un_contenu_illisible_vaut_profil_vide(db, store):
    store.record_push("dev", [1.0, 1.0, 1.0, 0.0], set())
    with Session(db) as session:
        row = session.get(DeveloperProfile, "dev")
        row.history = "{pas du json"
        session.add(row)
        session.commit()
    assert store.get_profile("dev").history == []


def test_les_statistiques_comptent_profils_et_pushs(store):
    store.record_push("alice", [1.0, 1.0, 1.0, 0.0], set())
    store.record_push("alice", [2.0, 1.0, 1.0, 0.0], set())
    store.record_push("bob", [3.0, 1.0, 1.0, 0.0], set())
    assert store.stats() == {"developer_count": 2, "total_pushs_observed": 3}


# --- calcul du score ----------------------------------------------------------------

def test_sans_historique_le_score_est_neutre_et_annonce_comme_tel():
    result = calculate_anomaly_score(push(), Profile())
    assert result["anomaly_score"] == 0.0 and result["profile_status"] == "cold_start"
    assert "Historique insuffisant" in result["explanation"][0]


def test_le_calcul_n_ecrit_rien_l_appelant_enregistre(store):
    result = calculate_anomaly_score(push(), Profile())
    assert store.stats()["developer_count"] == 0
    store.record_push("dev", result["features"], result["changed_files"])
    assert store.get_profile("dev").history == [result["features"]]


def test_un_push_hors_norme_sort_du_lot_et_s_explique():
    # Historique légèrement varié : sur des vecteurs tous identiques,
    # IsolationForest n'a rien à séparer et note tout le monde pareil.
    habituel = [[13.0 + i % 3, 2.0 + i % 4, 1.0 + i % 2, 0.0] for i in range(MIN_HISTORY_FOR_MODEL + 4)]
    profile = Profile(history=habituel, known_files=[f"src/{i}.py" for i in range(3)])

    normal = calculate_anomaly_score(push(), profile)
    assert normal["profile_status"] == "established"

    nocturne = calculate_anomaly_score(push(hour=3, files=120, commits=40), profile)
    assert nocturne["anomaly_score"] > normal["anomaly_score"]
    explication = " ".join(nocturne["explanation"])
    assert "l'heure du push" in explication and "le nombre de fichiers modifiés" in explication


@pytest.mark.anyio
async def test_le_point_d_entree_enregistre_le_push(db):
    from app.ai import get_anomaly_score, get_profile_stats

    with Session(db) as session:
        result = await get_anomaly_score(session, "demo", "a" * 40, "dev", {"hour_of_day": 9, "files_changed": 2, "commit_count": 1, "changed_file_paths": ["a.py", "b.py"]})
        assert result["score"] == 0.0 and "Historique insuffisant" in result["explanation"]
        assert get_profile_stats(session) == {"developer_count": 1, "total_pushs_observed": 1}
        assert json.loads(session.get(DeveloperProfile, "dev").known_files) == ["a.py", "b.py"]
