"""
Module Notifications & Alertes, envoi d'e-mails via SMTP (bibliothèque
standard `smtplib`, aucune dépendance externe) quand un pipeline est bloqué,
mis en attente, ou qu'une dérogation est accordée.

Deux temps, et c'est ce qui les rend fiables : la préparation lit la base
(module actif, configuration, destinataires) et produit un message ; l'envoi
part dans la file de travail, où un SMTP momentanément injoignable est
réessayé au lieu d'être perdu. Le flow d'analyse ou la dérogation qui
déclenche la notification n'attend jamais le serveur SMTP, et ne peut pas
échouer à cause de lui.
"""
import logging
import smtplib
from dataclasses import dataclass
from email.mime.text import MIMEText

from sqlmodel import Session, select

from app.core.crypto import secret_box
from app.models.module_state import ModuleState
from app.models.notification_config import NotificationConfig
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Message:
    """Notification prête à partir : plus aucune lecture en base n'est nécessaire pour l'envoyer."""

    recipients: list[str]
    subject: str
    body: str


def _is_module_active(session: Session) -> bool:
    state = session.get(ModuleState, "notifications")
    return state.is_active if state else False


def _get_config(session: Session) -> NotificationConfig | None:
    config = session.exec(select(NotificationConfig).where(NotificationConfig.id == 1)).first()
    if not config or not config.smtp_host or not config.from_address:
        return None
    return config


def _enabled_config(session: Session) -> NotificationConfig | None:
    """Configuration utilisable : module actif ET SMTP renseigné, sinon rien à envoyer."""
    return _get_config(session) if _is_module_active(session) else None


def send_email(config: NotificationConfig, to_addrs: list[str], subject: str, body: str) -> None:
    """Envoi synchrone (smtplib est bloquant), toujours appelé depuis un thread (voir app/orchestration)."""
    if not to_addrs:
        return

    password = secret_box.decrypt(config.smtp_password) if config.smtp_password else ""

    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = config.from_address
    message["To"] = ", ".join(to_addrs)

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as server:
        if config.smtp_use_tls:
            server.starttls()
        if config.smtp_user and password:
            server.login(config.smtp_user, password)
        server.sendmail(config.from_address, to_addrs, message.as_string())


def _admin_and_security_officer_emails(session: Session) -> list[str]:
    users = session.exec(
        select(User).where(
            User.role.in_([UserRole.ADMIN, UserRole.SECURITY_OFFICER]),  # type: ignore[attr-defined]
            User.is_active == True,  # noqa: E712
        )
    ).all()
    return [u.email for u in users if u.email]


def prepare_waiting_or_blocked(session: Session, *, repository: str, commit_hash: str, decision: str, justification: str) -> Message | None:
    """Message pour une décision WAITING_HUMAN ou BLOCKED, ou None si personne n'est à prévenir."""
    config = _enabled_config(session)
    if not config:
        return None
    if decision == "WAITING_HUMAN" and not config.notify_on_waiting_human:
        return None
    if decision == "BLOCKED" and not config.notify_on_blocked:
        return None

    recipients = _admin_and_security_officer_emails(session)
    if not recipients:
        return None

    label = "en attente de validation" if decision == "WAITING_HUMAN" else "bloqué"
    return Message(
        recipients=recipients,
        subject=f"[Orchestrateur] Pipeline {label} : {repository}",
        body=(
            f"Le pipeline {repository} ({commit_hash[:12]}) est {label}.\n\n"
            f"{justification}\n\n"
            "Consultez la page Décisions du Dashboard pour agir."
        ),
    )


def prepare_derogation_granted(
    session: Session, *, repository: str, commit_hash: str, developer_username: str, approved_by: str, four_eyes_approved_by: str
) -> Message | None:
    """Message pour une dérogation confirmée (règle des quatre yeux), ou None si personne n'est à prévenir."""
    config = _enabled_config(session)
    if not config or not config.notify_on_derogation:
        return None

    developer = session.exec(select(User).where(User.username == developer_username)).first()
    recipients = _admin_and_security_officer_emails(session)
    if developer and developer.email:
        recipients.append(developer.email)
    recipients = list(dict.fromkeys(recipients))  # dédoublonnage en conservant l'ordre
    if not recipients:
        return None

    return Message(
        recipients=recipients,
        subject=f"[Orchestrateur] Dérogation accordée : {repository}",
        body=(
            f"Une dérogation a été accordée pour le pipeline {repository} ({commit_hash[:12]}).\n\n"
            f"Première validation : {approved_by}\n"
            f"Seconde validation (règle des 4 yeux) : {four_eyes_approved_by}\n\n"
            "Le déploiement a été déclenché."
        ),
    )


def deliver(session: Session, message: Message) -> None:
    """
    Envoi effectif, exécuté par le job de la file (jobs.py). Relit la
    configuration au moment de l'envoi : un réessai part avec les réglages
    du moment, pas avec ceux d'il y a une heure. Laisse remonter l'erreur
    SMTP, c'est elle qui déclenche le réessai.
    """
    config = _enabled_config(session)
    if not config:
        logger.info("Notification abandonnée : module désactivé ou configuration SMTP retirée depuis la mise en file.")
        return
    send_email(config, message.recipients, message.subject, message.body)


def notify_waiting_or_blocked(session: Session, **kwargs) -> None:
    """Appelé depuis decision_engine.py juste après avoir tranché WAITING_HUMAN ou BLOCKED."""
    _dispatch(session, prepare_waiting_or_blocked(session, **kwargs))


def notify_derogation_granted(session: Session, **kwargs) -> None:
    """Appelé depuis routes_decisions.py une fois la seconde validation (4 yeux) confirmée."""
    _dispatch(session, prepare_derogation_granted(session, **kwargs))


def _dispatch(session: Session, message: Message | None) -> None:
    """
    Met le message en file. Sans file de travail (développement sans
    PostgreSQL, tests), on envoie sur place plutôt que de perdre la
    notification : best-effort dans les deux cas, jamais d'exception.
    """
    if message is None:
        return
    # Import local : jobs.py importe les flows, qui importent ce module.
    from app.orchestration.jobs import defer_notification

    try:
        defer_notification(message)
    except Exception as e:
        logger.warning(f"Mise en file impossible ({e}), envoi direct de la notification « {message.subject} ».")
        try:
            deliver(session, message)
        except Exception as error:
            logger.warning(f"Échec d'envoi de la notification « {message.subject} » : {error}")
