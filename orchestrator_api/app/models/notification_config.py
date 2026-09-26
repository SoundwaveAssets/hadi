from typing import Optional

from sqlmodel import Field, SQLModel


class NotificationConfig(SQLModel, table=True):
    """
    Configuration du module Notifications & Alertes, ligne unique (id=1),
    même convention que ToolConfig. Un serveur SMTP interne/d'entreprise,
    jamais un service tiers imposé : reste cohérent avec la portabilité
    100% de l'Orchestrateur (aucune dépendance à un fournisseur externe
    obligatoire, juste un serveur SMTP quelconque que l'administrateur
    renseigne).
    """

    __tablename__ = "notification_config"

    id: Optional[int] = Field(default=None, primary_key=True)

    smtp_host: Optional[str] = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_user: Optional[str] = Field(default=None)
    smtp_password: Optional[str] = Field(default=None)  # chiffré (secret_box), comme les jetons d'outils
    smtp_use_tls: bool = Field(default=True)
    from_address: Optional[str] = Field(default=None)

    notify_on_waiting_human: bool = Field(default=True, description="E-mail aux admins/responsables sécurité")
    notify_on_blocked: bool = Field(default=True, description="E-mail aux admins/responsables sécurité")
    notify_on_derogation: bool = Field(default=True, description="E-mail au développeur concerné une fois la dérogation accordée")
