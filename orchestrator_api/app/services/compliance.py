"""
Module Politiques de conformité, applique les règles personnalisées
(app/models/compliance_policy.py) en plus de la décision SonarQube/IA
(decision_engine.py). Ne peut jamais assouplir une décision, seulement la
durcir : AUTO_AUTH -> WAITING_HUMAN si une politique s'y oppose, jamais
l'inverse (principe fail-closed).
"""
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models.compliance_policy import CompliancePolicy, CompliancePolicyType
from app.models.module_state import ModuleState


def _is_module_active(session: Session) -> bool:
    state = session.get(ModuleState, "compliance_policies")
    return state.is_active if state else False


def _within_any_window(policies: list[CompliancePolicy], now: datetime) -> bool:
    """Autorisé si AU MOINS UNE fenêtre active couvre l'instant présent (union des fenêtres)."""
    weekday = now.weekday()  # 0=lundi..6=dimanche, cohérent avec allowed_days
    hour = now.hour
    for p in policies:
        days_ok = True
        if p.allowed_days:
            allowed = {int(d) for d in p.allowed_days.split(",") if d.strip().isdigit()}
            days_ok = weekday in allowed
        hours_ok = True
        if p.allowed_start_hour is not None and p.allowed_end_hour is not None:
            if p.allowed_start_hour <= p.allowed_end_hour:
                hours_ok = p.allowed_start_hour <= hour < p.allowed_end_hour
            else:
                # Fenêtre à cheval sur minuit (ex. 22h -> 6h).
                hours_ok = hour >= p.allowed_start_hour or hour < p.allowed_end_hour
        if days_ok and hours_ok:
            return True
    return False


def apply_compliance_policies(
    session: Session, *, repository: str, decision: str, justification: str
) -> tuple[str, str]:
    """
    Reçoit la décision déjà tranchée par decision_engine.py et la durcit si
    une politique active l'exige. Renvoie (decision, justification), inchangés
    si le module est désactivé, si aucune politique n'existe, ou si la
    décision d'origine est déjà BLOCKED (rien de plus sévère à appliquer).
    """
    if not _is_module_active(session) or decision == "BLOCKED":
        return decision, justification

    policies = session.exec(select(CompliancePolicy).where(CompliancePolicy.is_active == True)).all()  # noqa: E712
    if not policies:
        return decision, justification

    # --- Dépôts soumis à examen renforcé : jamais d'AUTO_AUTH ---
    reinforced = [
        p
        for p in policies
        if p.policy_type == CompliancePolicyType.REINFORCED_REPOSITORY
        and p.repository_pattern
        and p.repository_pattern.lower() in repository.lower()
    ]
    if reinforced and decision == "AUTO_AUTH":
        names = ", ".join(p.name for p in reinforced)
        return "WAITING_HUMAN", (
            f"Validation manuelle requise : dépôt soumis à examen renforcé ({names})." " " + justification
        )

    # --- Fenêtres de déploiement autorisées ---
    # Sans repository_scope, la fenêtre vaut pour tous les dépôts ; avec, pour
    # celui qu'elle désigne.
    windows = [
        p
        for p in policies
        if p.policy_type == CompliancePolicyType.DEPLOYMENT_WINDOW
        and (not p.repository_scope or p.repository_scope == repository)
    ]
    if windows and decision == "AUTO_AUTH" and not _within_any_window(windows, datetime.now(timezone.utc)):
        return "WAITING_HUMAN", (
            "Validation manuelle requise : hors fenêtre de déploiement autorisée "
            f"(politique de conformité, heure actuelle UTC {datetime.now(timezone.utc).strftime('%H:%M')})."
            " " + justification
        )

    return decision, justification
