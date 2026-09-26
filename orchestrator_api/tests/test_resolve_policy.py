"""
Tests de la résolution des réglages effectifs (couche application).

`resolve_policy` lit ses entrées par `getattr`, donc de simples objets factices
suffisent : pas besoin d'une base, ni même d'instancier les modèles SQLModel.
"""
from types import SimpleNamespace

from app.decision_engine import DEFAULT_THRESHOLDS, resolve_policy


def pipeline(**kwargs) -> SimpleNamespace:
    base = dict(
        anomaly_review_threshold=None,
        anomaly_block_threshold=None,
        ai_observation_mode=None,
        decision_engine_enabled=True,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def global_config(**kwargs) -> SimpleNamespace:
    base = dict(anomaly_review_threshold=0.5, anomaly_block_threshold=0.8, ai_observation_mode=True)
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_sans_configuration_on_retombe_sur_les_defauts():
    policy = resolve_policy(None, None)
    assert policy.thresholds == DEFAULT_THRESHOLDS
    assert policy.observation_mode is True
    assert policy.engine_enabled is True


def test_le_pipeline_surcharge_le_reglage_global():
    policy = resolve_policy(
        pipeline(anomaly_review_threshold=0.2, anomaly_block_threshold=0.4),
        global_config(anomaly_review_threshold=0.5, anomaly_block_threshold=0.8),
    )
    assert (policy.thresholds.review, policy.thresholds.block) == (0.2, 0.4)


def test_une_surcharge_partielle_herite_du_reste():
    policy = resolve_policy(
        pipeline(anomaly_review_threshold=0.1),
        global_config(anomaly_block_threshold=0.9),
    )
    assert policy.thresholds.review == 0.1
    assert policy.thresholds.block == 0.9


def test_observation_false_sur_le_pipeline_est_respecte():
    """`False` ne doit pas être confondu avec `None` : c'est une surcharge explicite."""
    policy = resolve_policy(pipeline(ai_observation_mode=False), global_config(ai_observation_mode=True))
    assert policy.observation_mode is False


def test_des_seuils_inverses_en_base_ne_font_pas_echouer_lanalyse():
    """
    Rien ne validait ces valeurs à l'écriture. Une analyse en cours ne doit pas
    mourir dessus : repli sur les défauts, et trace en erreur.
    """
    policy = resolve_policy(
        pipeline(anomaly_review_threshold=0.95, anomaly_block_threshold=0.10), None
    )
    assert policy.thresholds == DEFAULT_THRESHOLDS


def test_des_seuils_hors_intervalle_en_base_font_le_meme_repli():
    policy = resolve_policy(pipeline(anomaly_review_threshold=42.0), None)
    assert policy.thresholds == DEFAULT_THRESHOLDS


def test_le_bouton_durgence_du_pipeline_est_lu():
    assert resolve_policy(pipeline(decision_engine_enabled=False), None).engine_enabled is False
