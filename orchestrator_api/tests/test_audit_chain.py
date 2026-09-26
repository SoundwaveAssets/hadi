"""
Tests du chaînage d'intégrité du journal d'audit.

Le test central est `test_un_attaquant_sans_cle_ne_peut_pas_resceller` : c'est
lui qui distingue un vrai scellement d'un simple condensat public. Il échouait
par construction sur l'implémentation précédente (SHA-256 nu).
"""
from app.domain.audit_chain import seal, verify_chain, verify_entry

KEY = b"cle-de-test-strictement-locale-32b"
AUTRE_CLE = b"une-autre-cle-tout-aussi-locale-x"


def entry(**overrides) -> dict:
    base = {
        "id": 1,
        "timestamp": "2026-09-17T10:00:00+00:00",
        "developer_username": "didier",
        "repository_name": "orchestrator",
        "commit_hash": "a1b2c3d4",
        "ai_anomaly_score": 0.12,
        "ai_explanation": "Comportement conforme au profil habituel.",
        "sonarqube_vulnerabilities": 0,
        "decision": "AUTO_AUTH",
        "justification": "Toutes les vérifications sont au vert.",
        "approved_by": None,
        "four_eyes_approved_by": None,
        "supersedes_audit_id": None,
    }
    base.update(overrides)
    return base


def sealed_chain(count: int, *, key: bytes = KEY) -> list[dict]:
    entries: list[dict] = []
    previous = None
    for index in range(1, count + 1):
        item = entry(id=index, commit_hash=f"commit{index:04d}")
        item["entry_hash"] = seal(item, previous, key=key)
        entries.append(item)
        previous = item["entry_hash"]
    return entries


def test_une_chaine_intacte_est_verifiee():
    assert verify_chain(sealed_chain(5), key=KEY) == (True, None)


def test_une_alteration_est_detectee_et_localisee():
    chain = sealed_chain(5)
    chain[2]["decision"] = "AUTO_AUTH"
    chain[2]["justification"] = "Dérogation silencieuse."
    intact, faulty_id = verify_chain(chain, key=KEY)
    assert not intact
    assert faulty_id == 3


def test_une_suppression_rompt_la_chaine():
    chain = sealed_chain(5)
    del chain[2]
    intact, faulty_id = verify_chain(chain, key=KEY)
    assert not intact
    assert faulty_id == 4  # la première entrée dont le chaînage ne retombe plus


def test_un_attaquant_sans_cle_ne_peut_pas_resceller():
    """
    Le scénario que le modèle de menace annonce : quelqu'un a l'écriture
    directe sur PostgreSQL. Il modifie une ligne, puis rescelle toute la suite
    de la chaîne avec l'algorithme, public, du dépôt.

    Avec un SHA-256 nu, cette attaque réussit : rien ne manque à l'attaquant.
    Avec un HMAC, il lui manque la clé, et la vérification le voit.
    """
    chain = sealed_chain(4)
    chain[1]["decision"] = "AUTO_AUTH"
    chain[1]["justification"] = "Rien à signaler."

    previous = chain[0]["entry_hash"]
    for item in chain[1:]:
        item["entry_hash"] = seal(item, previous, key=AUTRE_CLE)
        previous = item["entry_hash"]

    intact, faulty_id = verify_chain(chain, key=KEY)
    assert not intact
    assert faulty_id == 2


def test_un_champ_hors_perimetre_ne_casse_pas_le_sceau():
    """
    Ajouter une colonne au modèle ne doit pas invalider rétroactivement les
    entrées déjà scellées, seuls les champs de SEALED_FIELDS comptent.
    """
    item = entry()
    digest = seal(item, None, key=KEY)
    item["entry_hash"] = digest
    item["sonarqube_metrics"] = '{"coverage": 42.0}'
    assert verify_entry(item, None, key=KEY)


def test_lordre_des_cles_du_dictionnaire_est_sans_effet():
    item = entry()
    inverse = dict(reversed(list(item.items())))
    assert seal(item, None, key=KEY) == seal(inverse, None, key=KEY)
