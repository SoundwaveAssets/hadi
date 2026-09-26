"""
Tests de la règle de décision.

Aucun de ces tests n'ouvre une connexion, ne lit un fichier, ni ne démarre un
thread : la règle est une fonction pure. C'est précisément ce que la version
précédente rendait impossible, et c'est pourquoi elle n'avait aucun test.
"""
import pytest

from app.domain.decision import (
    UNVERIFIABLE,
    Decision,
    EnginePolicy,
    Evidence,
    SecurityCriterion,
    Thresholds,
    decide,
    harden,
)

STRICT = EnginePolicy(thresholds=Thresholds(review=0.5, block=0.8), observation_mode=False)
OBSERVING = EnginePolicy(thresholds=Thresholds(review=0.5, block=0.8), observation_mode=True)


def evidence(*, build=True, vulns=0, score: float | None = 0.0, new_vulns=None, gate=None, failed=()) -> Evidence:
    """Par défaut, le code neuf porte le même compte que le projet : les tests
    historiques gardent leur sens, ceux qui distinguent les deux le disent."""
    return Evidence(
        build_succeeded=build,
        anomaly_score=score,
        vulnerabilities=vulns,
        new_vulnerabilities=vulns if new_vulns is None else new_vulns,
        quality_gate=gate,
        failed_gate_conditions=failed,
    )


# --- Garde-fou principal : le fail-closed ---------------------------------

def test_analyse_non_verifiable_ne_passe_jamais_pour_un_vert():
    """
    Régression du défaut le plus grave du moteur précédent.

    Quand SonarQube est injoignable ou que la métrique est absente de sa
    réponse, l'ancien code retombait sur `default=0`, indistinguable de
    « vérifié, zéro vulnérabilité », et autorisait le déploiement.
    """
    verdict = decide(evidence(vulns=UNVERIFIABLE), STRICT)
    assert verdict.decision is Decision.WAITING_HUMAN
    assert "non vérifiable" in verdict.justification


def test_zero_vulnerabilite_verifiee_autorise():
    assert decide(evidence(vulns=0), STRICT).decision is Decision.AUTO_AUTH


def test_build_en_echec_bloque_avant_toute_autre_consideration():
    verdict = decide(evidence(build=False, vulns=0, score=0.0), STRICT)
    assert verdict.decision is Decision.BLOCKED
    assert not verdict.behaviour_was_decisive


def test_build_en_echec_bloque_meme_moteur_desactive():
    policy = EnginePolicy(thresholds=Thresholds(0.5, 0.8), engine_enabled=False)
    assert decide(evidence(build=False), policy).decision is Decision.BLOCKED


# --- Combinaison des deux dimensions --------------------------------------

def test_vulnerabilite_seule_demande_une_validation_humaine():
    assert decide(evidence(vulns=3), STRICT).decision is Decision.WAITING_HUMAN


def test_anomalie_seule_demande_une_validation_humaine():
    assert decide(evidence(score=0.6), STRICT).decision is Decision.WAITING_HUMAN


def test_anomalie_critique_et_vulnerabilite_bloquent():
    verdict = decide(evidence(vulns=2, score=0.9), STRICT)
    assert verdict.decision is Decision.BLOCKED
    assert verdict.behaviour_was_decisive


def test_anomalie_critique_seule_ne_bloque_pas():
    """Une seule dimension ne doit jamais suffire à bloquer, seulement à mettre en attente."""
    assert decide(evidence(vulns=0, score=0.95), STRICT).decision is Decision.WAITING_HUMAN


# --- Mode observation ------------------------------------------------------

def test_mode_observation_neutralise_le_score_mais_le_trace():
    verdict = decide(evidence(vulns=0, score=0.95), OBSERVING)
    assert verdict.decision is Decision.AUTO_AUTH
    assert not verdict.behaviour_was_decisive
    assert "0.95" in verdict.justification


def test_mode_observation_ne_neutralise_pas_la_dimension_securite():
    assert decide(evidence(vulns=4, score=0.0), OBSERVING).decision is Decision.WAITING_HUMAN


# --- Moteur désactivé ------------------------------------------------------

def test_moteur_desactive_autorise_mais_trace_les_preuves():
    policy = EnginePolicy(thresholds=Thresholds(0.5, 0.8), engine_enabled=False)
    verdict = decide(evidence(vulns=7, score=0.99), policy)
    assert verdict.decision is Decision.AUTO_AUTH
    assert "7 vulnérabilité(s)" in verdict.justification
    assert "0.99" in verdict.justification


# --- Validation des seuils -------------------------------------------------

def test_seuils_inverses_refuses_a_la_construction():
    with pytest.raises(ValueError, match="ne peut pas dépasser"):
        Thresholds(review=0.9, block=0.3)


@pytest.mark.parametrize("bad", [-0.1, 1.5, 12.0])
def test_seuils_hors_intervalle_refuses(bad):
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        Thresholds(review=bad, block=1.0)


# --- Durcissement par politique de conformité ------------------------------

def test_le_durcissement_ne_touche_que_les_autorisations():
    autorise = decide(evidence(), STRICT)
    durci = harden(autorise, "dépôt soumis à examen renforcé")
    assert durci.decision is Decision.WAITING_HUMAN
    assert "examen renforcé" in durci.justification


def test_le_durcissement_ne_peut_jamais_assouplir():
    bloque = decide(evidence(build=False), STRICT)
    assert harden(bloque, "hors fenêtre de déploiement") == bloque


# --- Critère de sécurité : sur quoi le moteur juge un commit ----------------

def policy(criterion: SecurityCriterion) -> EnginePolicy:
    return EnginePolicy(thresholds=Thresholds(review=0.5, block=0.8), observation_mode=False, security_criterion=criterion)


def test_la_dette_ancienne_ne_bloque_plus_un_commit_propre():
    """
    Le défaut corrigé : un dépôt qui traîne 40 vulnérabilités mettait en
    attente TOUS ses pushs, y compris celui qui n'introduit rien et même
    celui qui en corrige. Le critère par défaut ne regarde que le code neuf.
    """
    propre = evidence(vulns=40, new_vulns=0)
    assert decide(propre, policy(SecurityCriterion.NEW_CODE)).decision is Decision.AUTO_AUTH
    assert decide(propre, policy(SecurityCriterion.TOTAL)).decision is Decision.WAITING_HUMAN


def test_une_vulnerabilite_introduite_par_ce_commit_arrete_tout():
    verdict = decide(evidence(vulns=41, new_vulns=1), policy(SecurityCriterion.NEW_CODE))
    assert verdict.decision is Decision.WAITING_HUMAN
    assert "code neuf" in verdict.justification


def test_code_neuf_non_mesure_vaut_non_verifiable_pas_zero():
    """Fail-closed : une période de code neuf non configurée ne vaut pas « rien de neuf »."""
    verdict = decide(evidence(vulns=0, new_vulns=UNVERIFIABLE), policy(SecurityCriterion.NEW_CODE))
    assert verdict.decision is Decision.WAITING_HUMAN
    assert "non vérifiable" in verdict.justification and "période de code neuf" in verdict.justification


@pytest.mark.parametrize(
    "gate, attendu",
    [("OK", Decision.AUTO_AUTH), ("ERROR", Decision.WAITING_HUMAN), (None, Decision.WAITING_HUMAN)],
)
def test_quality_gate_sonarqube_comme_critere(gate, attendu):
    assert decide(evidence(vulns=40, gate=gate), policy(SecurityCriterion.QUALITY_GATE)).decision is attendu


def test_le_quality_gate_en_echec_nomme_ses_conditions():
    verdict = decide(
        evidence(gate="ERROR", failed=("new_security_rating", "new_coverage")),
        policy(SecurityCriterion.QUALITY_GATE),
    )
    assert "new_security_rating" in verdict.justification and "new_coverage" in verdict.justification


def test_aucun_repli_silencieux_d_un_critere_sur_un_autre():
    """
    Un critère indisponible met en attente en le disant, il n'emprunte pas
    la mesure d'un autre : une décision doit rester explicable en audit.
    """
    aveugle = evidence(vulns=0, new_vulns=UNVERIFIABLE, gate=None)
    assert decide(aveugle, policy(SecurityCriterion.NEW_CODE)).decision is Decision.WAITING_HUMAN
    assert decide(aveugle, policy(SecurityCriterion.QUALITY_GATE)).decision is Decision.WAITING_HUMAN
    assert decide(aveugle, policy(SecurityCriterion.TOTAL)).decision is Decision.AUTO_AUTH


# --- Score comportemental non mesuré ---------------------------------------

def test_un_moteur_d_anomalies_en_panne_ne_passe_pas_pour_un_comportement_normal():
    """
    Symétrique d'UNVERIFIABLE côté sécurité : une panne du moteur produisait
    un score 0.0 scellé, indiscernable d'un push mesuré comme conforme, donc
    potentiellement autorisé automatiquement.
    """
    verdict = decide(evidence(score=None), STRICT)
    assert verdict.decision is Decision.WAITING_HUMAN
    assert "non calculable" in verdict.justification
    assert verdict.behaviour_was_decisive is True


def test_en_mode_observation_un_score_absent_ne_change_rien():
    """Le moteur n'est pas décisionnel : son indisponibilité ne doit bloquer personne."""
    assert decide(evidence(score=None), OBSERVING).decision is Decision.AUTO_AUTH


def test_un_score_absent_ne_bloque_jamais_seul_meme_avec_un_probleme_de_securite():
    """On demande un humain, on ne bloque pas : une panne d'outil n'est pas une preuve à charge."""
    verdict = decide(evidence(score=None, vulns=3), STRICT)
    assert verdict.decision is Decision.WAITING_HUMAN
