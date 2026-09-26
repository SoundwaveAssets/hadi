"""
Règle de décision : autoriser, mettre en attente, ou bloquer un déploiement.

Fonction pure, mêmes entrées, mêmes sorties, aucun effet de bord. La collecte
des preuves (Jenkins, SonarQube, moteur d'anomalies) et la persistance du
verdict appartiennent à la couche application, jamais ici.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    AUTO_AUTH = "AUTO_AUTH"
    WAITING_HUMAN = "WAITING_HUMAN"
    BLOCKED = "BLOCKED"


class DeploymentOutcome(str, Enum):
    """
    Issue d'un déploiement, journalisée APRÈS coup.

    Le journal prouvait la décision, jamais l'acte : « autorisé » était
    scellé, « déployé, image observée sur le cluster » ne vivait que dans une
    colonne de texte modifiable. Ces valeurs partagent la chaîne des
    décisions, mais n'en sont pas : elles ne répondent à aucun point de
    contrôle et n'attendent aucune validation (voir is_decision).
    """

    DEPLOYED = "DEPLOYED"
    FAILED = "DEPLOY_FAILED"


#: Ce qui est une issue de déploiement, et non un verdict.
OUTCOME_VALUES: frozenset[str] = frozenset(outcome.value for outcome in DeploymentOutcome)


def is_decision(value: str | None) -> bool:
    """Vrai pour un verdict (ce sur quoi un point de contrôle ou une validation se prononce)."""
    return value is not None and value not in OUTCOME_VALUES


class SecurityCriterion(str, Enum):
    """
    Ce qu'on regarde pour dire qu'un commit pose un problème de sécurité.

    NEW_CODE (défaut) : les vulnérabilités de la période de code neuf. Le seul
    critère cohérent avec une décision par commit : un dépôt endetté ne bloque
    pas les pushs qui réduisent sa dette.
    QUALITY_GATE : le verdict du Quality Gate, donc plus que la sécurité.
    TOTAL : la dette complète, pour qui exige zéro vulnérabilité.
    """

    NEW_CODE = "new_code"
    QUALITY_GATE = "quality_gate"
    TOTAL = "total"


#: Analyse de sécurité non obtenue. Distinct de 0, qui vaut « vérifié, aucune
#: vulnérabilité » : les confondre ferait passer une analyse manquante pour une
#: analyse au vert.
UNVERIFIABLE = -1


@dataclass(frozen=True)
class Thresholds:
    """Seuils du score d'anomalie. Validés à la construction, pas à l'usage."""

    review: float
    block: float

    def __post_init__(self) -> None:
        for name, value in (("mise en attente", self.review), ("blocage", self.block)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"Seuil de {name} hors de l'intervalle [0, 1] : {value!r}.")
        if self.review > self.block:
            # Seuils inversés : un score pourrait être « critique » sans jamais
            # être « inhabituel », ce qui rend la règle incohérente au lieu de
            # simplement plus stricte.
            raise ValueError(
                f"Le seuil de mise en attente ({self.review}) ne peut pas dépasser "
                f"le seuil de blocage ({self.block})."
            )


#: Verdict d'un Quality Gate SonarQube tel que l'API le renvoie.
GATE_PASSED = "OK"
GATE_FAILED = "ERROR"


@dataclass(frozen=True)
class SecurityStatus:
    """Lecture d'un critère de sécurité : vérifiable ou non, en alerte ou non, et pourquoi."""

    verifiable: bool
    concern: bool
    summary: str


@dataclass(frozen=True)
class Evidence:
    """Ce qui a été réellement observé pour un commit donné."""

    build_succeeded: bool
    #: None = le moteur d'anomalies n'a rien pu mesurer (panne, modèle
    #: indisponible). Distinct de 0.0, qui veut dire « mesuré, conforme » :
    #: les confondre fait passer une panne pour un comportement nominal, le
    #: même défaut que UNVERIFIABLE corrige côté sécurité.
    anomaly_score: float | None
    #: Dette de sécurité du projet entier, toutes antériorités confondues.
    vulnerabilities: int = UNVERIFIABLE
    #: Vulnérabilités introduites par la période de code neuf de SonarQube.
    new_vulnerabilities: int = UNVERIFIABLE
    #: Verdict du Quality Gate : "OK", "ERROR", ou None si non consulté/absent.
    quality_gate: str | None = None
    #: Conditions en échec du Quality Gate, pour que la justification les nomme.
    failed_gate_conditions: tuple[str, ...] = ()

    def describe_behaviour(self) -> str:
        if self.anomaly_score is None:
            return "score comportemental non calculable (moteur d'anomalies en erreur)"
        return f"score d'anomalie {self.anomaly_score:.2f}"

    def security(self, criterion: SecurityCriterion) -> SecurityStatus:
        """
        Lit le critère demandé, et lui seul : aucun repli silencieux sur un
        autre. Une donnée absente vaut « non vérifiable », donc alerte
        (fail-closed), avec un message qui dit quoi corriger : plutôt qu'un
        repli qui rendrait la décision imprévisible et inexplicable en audit.
        """
        if criterion is SecurityCriterion.QUALITY_GATE:
            return self._gate_status()
        if criterion is SecurityCriterion.NEW_CODE:
            return self._count_status(
                self.new_vulnerabilities,
                "code neuf",
                "métrique new_vulnerabilities absente : vérifiez qu'une période de code neuf est définie sur le projet SonarQube",
            )
        return self._count_status(
            self.vulnerabilities,
            "projet entier",
            "métrique vulnerabilities absente (SonarQube injoignable ou projet jamais analysé)",
        )

    def _count_status(self, count: int, scope: str, missing: str) -> SecurityStatus:
        if count == UNVERIFIABLE:
            return SecurityStatus(False, True, f"analyse de sécurité non vérifiable ({missing})")
        return SecurityStatus(
            True,
            count > 0,
            f"{count} vulnérabilité(s) SonarQube sur le {scope}",
        )

    def _gate_status(self) -> SecurityStatus:
        if self.quality_gate not in (GATE_PASSED, GATE_FAILED):
            return SecurityStatus(
                False, True, "Quality Gate SonarQube non vérifiable (aucun gate associé au projet ou API injoignable)"
            )
        if self.quality_gate == GATE_PASSED:
            return SecurityStatus(True, False, "Quality Gate SonarQube au vert")
        detail = f" ({', '.join(self.failed_gate_conditions)})" if self.failed_gate_conditions else ""
        return SecurityStatus(True, True, f"Quality Gate SonarQube en échec{detail}")


@dataclass(frozen=True)
class EnginePolicy:
    """Réglages effectifs applicables à ce pipeline (après résolution des surcharges)."""

    thresholds: Thresholds
    observation_mode: bool = True
    engine_enabled: bool = True
    security_criterion: SecurityCriterion = SecurityCriterion.NEW_CODE


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    justification: str
    #: Le score d'anomalie a-t-il réellement pesé sur cette décision ?
    #: Faux en mode observation, le score reste tracé, jamais décisionnaire.
    behaviour_was_decisive: bool


def decide(evidence: Evidence, policy: EnginePolicy) -> Verdict:
    """
    Ordre d'évaluation, du plus contraignant au plus permissif :

    Le problème de sécurité se lit selon `policy.security_criterion` : code
    neuf, Quality Gate, ou dette totale du projet (voir SecurityCriterion).

    1. Build en échec → blocage inconditionnel. Aucun artefact valide n'existe,
       il n'y a rien à déployer ; inutile de regarder plus loin.
    2. Moteur désactivé → autorisation, avec les preuves tout de même tracées.
    3. Anomalie critique ET problème de sécurité → blocage.
    4. L'une des deux dimensions seule → validation humaine.
    5. Sinon → autorisation automatique.
    """
    if not evidence.build_succeeded:
        return Verdict(
            Decision.BLOCKED,
            "Blocage automatique : le build Jenkins a échoué, aucun artefact valide à déployer. "
            "Une dérogation reste possible si le déploiement doit malgré tout être forcé.",
            behaviour_was_decisive=False,
        )

    security = evidence.security(policy.security_criterion)

    if not policy.engine_enabled:
        return Verdict(
            Decision.AUTO_AUTH,
            "Autorisation automatique : le Moteur de décision est désactivé pour ce pipeline. "
            f"{evidence.describe_behaviour()} et {security.summary} "
            "restent tracés, mais non décisionnels tant que le moteur reste désactivé.",
            behaviour_was_decisive=False,
        )

    security_concern = security.concern

    # En mode observation, le score est calculé et tracé mais ne pèse sur aucune
    # décision, le temps de mesurer sa fiabilité sur des données réelles.
    if policy.observation_mode:
        severe_anomaly = False
        behaviour_concern = False
    elif evidence.anomaly_score is None:
        # Moteur décisionnel mais aveugle : on ne bloque pas (ce serait un
        # déni de service au moindre incident), on demande un humain.
        severe_anomaly = False
        behaviour_concern = True
    else:
        severe_anomaly = evidence.anomaly_score >= policy.thresholds.block
        behaviour_concern = evidence.anomaly_score >= policy.thresholds.review

    if security_concern and severe_anomaly:
        verdict = Verdict(
            Decision.BLOCKED,
            f"Blocage automatique : anomalie comportementale critique "
            f"({evidence.describe_behaviour()}) combinée à un problème de sécurité du code "
            f"({security.summary}).",
            behaviour_was_decisive=True,
        )
    elif security_concern or behaviour_concern:
        reasons = []
        if security_concern:
            reasons.append(security.summary)
        if behaviour_concern:
            reasons.append(evidence.describe_behaviour())
        verdict = Verdict(
            Decision.WAITING_HUMAN,
            "Validation manuelle requise : " + " ; ".join(reasons) + ".",
            behaviour_was_decisive=behaviour_concern,
        )
    else:
        verdict = Verdict(
            Decision.AUTO_AUTH,
            "Toutes les vérifications sont au vert.",
            behaviour_was_decisive=False,
        )

    if policy.observation_mode and evidence.anomaly_score is not None and evidence.anomaly_score >= policy.thresholds.review:
        verdict = Verdict(
            verdict.decision,
            verdict.justification
            + f" [Mode observation actif : score {evidence.anomaly_score:.2f} tracé "
            "mais non pris en compte dans cette décision.]",
            verdict.behaviour_was_decisive,
        )

    return verdict


def harden(verdict: Verdict, reason: str) -> Verdict:
    """
    Durcit un verdict d'un cran (AUTO_AUTH → WAITING_HUMAN) sans jamais
    l'assouplir, c'est le seul sens dans lequel une politique de conformité
    a le droit d'agir sur une décision déjà rendue.
    """
    if verdict.decision is not Decision.AUTO_AUTH:
        return verdict
    return Verdict(
        Decision.WAITING_HUMAN,
        f"Validation manuelle requise : {reason}. {verdict.justification}",
        verdict.behaviour_was_decisive,
    )
