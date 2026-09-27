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
    # Fenêtre calée sur l'heure courante : l'heure de fin étant exclue, un
    # 0-23 en dur échouerait entre 23 h et minuit, une heure sur vingt-quatre.
    maintenant = datetime.now(timezone.utc)
    politique(
        session,
        policy_type=CompliancePolicyType.DEPLOYMENT_WINDOW,
        allowed_days=str(maintenant.weekday()),
        allowed_start_hour=maintenant.hour,
        allowed_end_hour=(maintenant.hour + 1) % 24,
    )
    assert appliquer(session)[0] == "AUTO_AUTH"


@pytest.mark.parametrize(
    ("heure", "attendu"),
    [(7, False), (8, True), (17, True), (18, False)],
)
def test_l_heure_de_fin_est_exclue(heure: int, attendu: bool):
    """Une fenêtre 8-18 couvre 8 h 00 à 17 h 59, pas 18 h."""
    from app.services.compliance import _within_any_window

    fenetre = CompliancePolicy(
        name="bureau",
        policy_type=CompliancePolicyType.DEPLOYMENT_WINDOW,
        created_by="test",
        allowed_start_hour=8,
        allowed_end_hour=18,
    )
    instant = datetime(2026, 1, 5, heure, 30, tzinfo=timezone.utc)  # un lundi
    assert _within_any_window([fenetre], instant) is attendu


def test_une_fenetre_a_cheval_sur_minuit():
    """22 h -> 6 h : la nuit est couverte, l'après-midi non."""
    from app.services.compliance import _within_any_window

    fenetre = CompliancePolicy(
        name="nuit",
        policy_type=CompliancePolicyType.DEPLOYMENT_WINDOW,
        created_by="test",
        allowed_start_hour=22,
        allowed_end_hour=6,
    )
    lundi = lambda h: datetime(2026, 1, 5, h, 30, tzinfo=timezone.utc)  # noqa: E731
    assert _within_any_window([fenetre], lundi(23)) is True
    assert _within_any_window([fenetre], lundi(3)) is True
    assert _within_any_window([fenetre], lundi(15)) is False


def test_une_fenetre_restreinte_a_un_autre_depot_ne_s_applique_pas(session):
    aujourd_hui = datetime.now(timezone.utc).weekday()  # lundi = 0, convention partagée avec le frontend
    autres_jours = ",".join(str(j) for j in range(7) if j != aujourd_hui)
    politique(session, policy_type=CompliancePolicyType.DEPLOYMENT_WINDOW, allowed_days=autres_jours, repository_scope="paiement")
    assert appliquer(session)[0] == "AUTO_AUTH"
