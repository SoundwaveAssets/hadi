"""
Couche application du Moteur de décision.

Sa seule responsabilité : rassembler les preuves, résoudre les réglages
effectifs, déléguer le verdict à `app.domain.decision` (pur), puis persister et
notifier. La RÈGLE elle-même n'est plus ici, c'est ce qui permet de la tester
sans PostgreSQL, sans Jenkins et sans SonarQube (voir tests/test_decision.py).
"""
import json
import logging

from sqlmodel import Session, select

from app.ai import get_anomaly_score
from app.domain.decision import (
    UNVERIFIABLE,
    Decision,
    EnginePolicy,
    Evidence,
    SecurityCriterion,
    Thresholds,
    Verdict,
    decide,
)
from app.models.audit import AuditLog, append_audit_log
from app.models.config import ToolConfig
from app.models.pipeline_config import PipelineConfig
from app.services.compliance import apply_compliance_policies
from app.services.notifier import notify_waiting_or_blocked
from app.services.pipeline_config import get_pipeline_config

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS = Thresholds(review=0.5, block=0.8)
DEFAULT_SECURITY_CRITERION = SecurityCriterion.NEW_CODE


def _first_not_none(*values):
    """Première valeur non nulle : surcharge du pipeline, puis réglage global, puis défaut."""
    for value in values:
        if value is not None:
            return value
    return None


def _resolve_criterion(pipeline_config, global_config) -> SecurityCriterion:
    """
    Critère de sécurité effectif. Une valeur inconnue en base (réglage écrit
    à la main, migration d'une version antérieure) ne doit pas faire échouer
    l'analyse : on retombe sur le défaut et on le dit.
    """
    raw = _first_not_none(
        getattr(pipeline_config, "security_criterion", None),
        getattr(global_config, "security_criterion", None),
        DEFAULT_SECURITY_CRITERION.value,
    )
    try:
        return SecurityCriterion(raw)
    except ValueError:
        logger.error(
            "Critère de sécurité inconnu en base (%r) : repli sur %s.", raw, DEFAULT_SECURITY_CRITERION.value
        )
        return DEFAULT_SECURITY_CRITERION


def resolve_policy(
    pipeline_config: PipelineConfig | None, global_config: ToolConfig | None
) -> EnginePolicy:
    """
    Réglages effectifs d'un pipeline : ce qu'il surcharge explicitement, sinon
    le réglage global, sinon le défaut.

    Des seuils incohérents en base (inversés, hors intervalle, rien ne les
    validait à l'écriture) ne doivent jamais faire échouer une analyse en
    cours : on retombe sur les défauts et on le signale bruyamment, plutôt que
    de laisser une ValueError tuer le flow et abandonner le pipeline sans
    décision ni trace.
    """
    review = _first_not_none(
        getattr(pipeline_config, "anomaly_review_threshold", None),
        getattr(global_config, "anomaly_review_threshold", None),
        DEFAULT_THRESHOLDS.review,
    )
    block = _first_not_none(
        getattr(pipeline_config, "anomaly_block_threshold", None),
        getattr(global_config, "anomaly_block_threshold", None),
        DEFAULT_THRESHOLDS.block,
    )
    try:
        thresholds = Thresholds(review=float(review), block=float(block))
    except (ValueError, TypeError) as error:
        logger.error(
            "Seuils de décision invalides en base (review=%r, block=%r) : %s. "
            "Repli sur les seuils par défaut %s/%s.",
            review, block, error, DEFAULT_THRESHOLDS.review, DEFAULT_THRESHOLDS.block,
        )
        thresholds = DEFAULT_THRESHOLDS

    return EnginePolicy(
        thresholds=thresholds,
        security_criterion=_resolve_criterion(pipeline_config, global_config),
        observation_mode=bool(
            _first_not_none(
                getattr(pipeline_config, "ai_observation_mode", None),
                getattr(global_config, "ai_observation_mode", None),
                True,
            )
        ),
        # Bouton d'urgence par pipeline. Un dépôt sans PipelineConfig n'atteint
        # jamais ce code (rejeté par le Webhook en amont), donc le défaut
        # "activé" ne s'applique qu'à un pipeline enregistré n'ayant pas touché
        # ce réglage.
        engine_enabled=(
            pipeline_config.decision_engine_enabled if pipeline_config is not None else True
        ),
    )


async def _collect_anomaly(session: Session, repository: str, commit_hash: str, author: str, metadata: dict) -> tuple[float | None, str | None]:
    """
    Score comportemental et son explication. Un échec ne fait jamais échouer
    l'analyse, mais il ne se déguise pas non plus en 0.0 : le score vaut None
    (« non mesuré ») et l'entrée d'audit le dit. Moteur décisionnel et score
    absent, c'est une validation humaine (voir domain/decision.py).
    """
    try:
        result = await get_anomaly_score(session, repository, commit_hash, author, metadata)
        return float(result["score"]), result["explanation"]
    except Exception as error:  # noqa: BLE001 - best-effort assumé, jamais silencieux
        logger.warning("Score d'anomalie indisponible pour %s/%s : %s", author, commit_hash[:7], error)
        return None, "Score comportemental non calculable (moteur d'anomalies en erreur)."


async def evaluate_pipeline_and_decide(
    session: Session,
    repository: str,
    commit_hash: str,
    author: str,
    ai_metadata: dict,
    sonar_metrics: dict,
    build_success: bool = True,
    identity_source: str | None = None,
) -> AuditLog:
    """
    Orchestration : preuves → verdict → durcissement conformité → audit → alerte.

    `sonar_metrics` est fourni par le flow (une seule interrogation de
    SonarQube par pipeline, avec ses retries) et jamais re-collecté ici.
    """
    anomaly_score, ai_explanation = await _collect_anomaly(
        session, repository, commit_hash, author, ai_metadata
    )

    evidence = Evidence(
        build_succeeded=build_success,
        anomaly_score=anomaly_score,
        # Défaut UNVERIFIABLE et non 0 : un dictionnaire de métriques sans la
        # clé attendue signifie "pas mesuré", pas "mesuré à zéro".
        vulnerabilities=int(sonar_metrics.get("vulnerabilities", UNVERIFIABLE)),
        new_vulnerabilities=int(sonar_metrics.get("new_vulnerabilities", UNVERIFIABLE)),
        quality_gate=sonar_metrics.get("quality_gate"),
        failed_gate_conditions=tuple(sonar_metrics.get("failed_gate_conditions") or ()),
    )

    policy = resolve_policy(
        get_pipeline_config(session, repository),
        session.exec(select(ToolConfig).where(ToolConfig.id == 1)).first(),
    )

    verdict: Verdict = decide(evidence, policy)

    # Module Politiques de conformité : ne peut que durcir (AUTO_AUTH →
    # WAITING_HUMAN), jamais assouplir. Sans effet si le module est désactivé.
    hardened_decision, hardened_justification = apply_compliance_policies(
        session,
        repository=repository,
        decision=verdict.decision.value,
        justification=verdict.justification,
    )

    saved_entry = append_audit_log(
        session,
        AuditLog(
            developer_username=author,
            developer_identity_source=identity_source,
            repository_name=repository,
            commit_hash=commit_hash,
            ai_anomaly_score=anomaly_score,
            ai_explanation=ai_explanation,
            # Dette du projet entier : sens historique de ce champ, conservé
            # tel quel. Le chiffre qui a réellement tranché dépend du critère
            # et se lit dans security_criterion + la justification.
            sonarqube_vulnerabilities=evidence.vulnerabilities,
            security_criterion=policy.security_criterion.value,
            sonarqube_metrics=json.dumps(sonar_metrics) if sonar_metrics else None,
            decision=hardened_decision,
            justification=hardened_justification,
        ),
    )

    if hardened_decision in (Decision.WAITING_HUMAN.value, Decision.BLOCKED.value):
        # Mise en file seulement : l'envoi SMTP appartient au job, avec ses
        # réessais. Une décision déjà actée n'attend pas un serveur de mail.
        await notify_waiting_or_blocked(
            session,
            repository=repository,
            commit_hash=commit_hash,
            decision=hardened_decision,
            justification=hardened_justification,
        )

    return saved_entry
