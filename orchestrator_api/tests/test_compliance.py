"""
Politiques de conformité : elles ne peuvent que DURCIR une décision déjà
rendue. C'est le seul sens autorisé, et rien ne le vérifiait.
"""
from datetime import datetime, timezone

import pytest
from sqlmodel import Session

from app.models.compliance_policy import CompliancePolicy, CompliancePolicyType
from app.services.compliance import apply_compliance_policies


@pytest.fixture
def session(db):
    with Session(db) as s:
        yield s


def politique(session, **kwargs) -> CompliancePolicy:
    defaults = {"name": "règle", "created_by": "admin", "is_active": True}
    policy = CompliancePolicy(**{**defaults, **kwargs})
    session.add(policy)
    session.commit()
    return policy


def appliquer(session, decision="AUTO_AUTH", repository="demo"):
    return apply_compliance_policies(session, repository=repository, decision=decision, justification="Tout est au vert.")


def test_sans_politique_la_decision_ne_bouge_pas(session):
    assert appliquer(session) == ("AUTO_AUTH", "Tout est au vert.")


def test_un_depot_sensible_impose_une_validation_humaine(session):
    politique(session, policy_type=CompliancePolicyType.REINFORCED_REPOSITORY, repository_pattern="demo")
    decision, justification = appliquer(session)
    assert decision == "WAITING_HUMAN" and "règle" in justification and "Tout est au vert." in justification


def test_une_politique_inactive_ne_s_applique_pas(session):
    politique(session, policy_type=CompliancePolicyType.REINFORCED_REPOSITORY, repository_pattern="demo", is_active=False)
    assert appliquer(session)[0] == "AUTO_AUTH"


def test_un_autre_depot_n_est_pas_concerne(session):
    politique(session, policy_type=CompliancePolicyType.REINFORCED_REPOSITORY, repository_pattern="paiement")
    assert appliquer(session)[0] == "AUTO_AUTH"


def test_une_politique_ne_peut_jamais_assouplir_un_blocage(session):
    """Le sens unique du durcissement : une règle de conformité ne débloque rien."""
    politique(session, policy_type=CompliancePolicyType.REINFORCED_REPOSITORY, repository_pattern="demo")
    for decision in ("BLOCKED", "WAITING_HUMAN"):
        assert appliquer(session, decision=decision)[0] == decision


def test_hors_fenetre_de_deploiement_la_validation_devient_humaine(session):
    """Fenêtre fermée : le jour courant n'est pas dans allowed_days."""
    aujourd_hui = datetime.now(timezone.utc).weekday()  # lundi = 0, convention partagée avec le frontend
    autres_jours = ",".join(str(j) for j in range(7) if j != aujourd_hui)
    politique(session, policy_type=CompliancePolicyType.DEPLOYMENT_WINDOW, allowed_days=autres_jours, allowed_start_hour=0, allowed_end_hour=23)
    assert appliquer(session)[0] == "WAITING_HUMAN"


def test_dans_la_fenetre_le_deploiement_automatique_reste_permis(session):
    aujourd_hui = datetime.now(timezone.utc).weekday()  # lundi = 0, convention partagée avec le frontend
    politique(session, policy_type=CompliancePolicyType.DEPLOYMENT_WINDOW, allowed_days=str(aujourd_hui), allowed_start_hour=0, allowed_end_hour=23)
    assert appliquer(session)[0] == "AUTO_AUTH"


def test_une_fenetre_restreinte_a_un_autre_depot_ne_s_applique_pas(session):
    aujourd_hui = datetime.now(timezone.utc).weekday()  # lundi = 0, convention partagée avec le frontend
    autres_jours = ",".join(str(j) for j in range(7) if j != aujourd_hui)
    politique(session, policy_type=CompliancePolicyType.DEPLOYMENT_WINDOW, allowed_days=autres_jours, repository_scope="paiement")
    assert appliquer(session)[0] == "AUTO_AUTH"
