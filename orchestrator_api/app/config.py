"""
Configuration de l'application : un seul objet, validé au démarrage.

Une variable mal typée fait échouer le lancement avec un message clair, plutôt
qu'un comportement surprenant trois heures plus tard en production.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Journalisation ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    #: "json" pour la production (ingestion Loki/Datadog/ELK), "text" pour le développement.
    log_format: str = Field(default="text", alias="LOG_FORMAT")

    # --- Exposition HTTP ---
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001", alias="CORS_ALLOWED_ORIGINS"
    )

    #: URL de l'Orchestrateur telle qu'un agent Jenkins la voit, injectée dans
    #: les Jenkinsfile générés.
    public_url: str = Field(default="http://localhost:8000", alias="ORCHESTRATOR_PUBLIC_URL")

    # --- Base de données (prioritaire sur le bootstrap local) ---
    db_host: Optional[str] = Field(default=None, alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: str = Field(default="", alias="DB_PASSWORD")
    db_name: str = Field(default="orchestrator_db", alias="DB_NAME")

    # --- Secrets applicatifs ---
    master_key: Optional[str] = Field(default=None, alias="ORCHESTRATOR_MASTER_KEY")
    jwt_secret: Optional[str] = Field(default=None, alias="ORCHESTRATOR_JWT_SECRET")
    #: Clé de scellement du journal d'audit (HMAC). Doit vivre HORS de la base
    #: qu'elle protège, sinon elle ne protège rien, voir domain/audit_chain.py.
    audit_key: Optional[str] = Field(default=None, alias="ORCHESTRATOR_AUDIT_KEY")
    #: Jeton exigé par l'assistant d'installation (voir core/setup_token.py).
    #: Vide : généré au premier démarrage et affiché dans les journaux.
    setup_token: Optional[str] = Field(default=None, alias="ORCHESTRATOR_SETUP_TOKEN")

    # --- File de travail ---
    #: Hôtes dont le certificat TLS n'est pas vérifié (`argocd.exemple:443`),
    #: séparés par des virgules. Vide : la vérification s'applique partout.
    tls_skip_verify_hosts: str = Field(default="", alias="ORCHESTRATOR_TLS_SKIP_VERIFY_HOSTS")

    #: Jobs exécutés en parallèle par cette instance (les jobs d'un même dépôt
    #: restent séquentiels, voir orchestration/jobs.py).
    worker_concurrency: int = Field(default=2, alias="ORCHESTRATOR_WORKER_CONCURRENCY")
    #: Délai sans progression au-delà duquel un pipeline PENDING ou DEPLOYING
    #: est repassé en échec (voir orchestration/watchdog.py).
    pipeline_stall_minutes: int = Field(default=120, alias="ORCHESTRATOR_PIPELINE_STALL_MINUTES")

    # --- Sessions ---
    #: Durée d'une session, prolongée tant que la personne travaille
    #: (POST /api/auth/refresh).
    jwt_expire_minutes: int = Field(default=120, alias="ORCHESTRATOR_JWT_EXPIRE_MINUTES")
    #: Inactivité au-delà de laquelle l'interface efface la session.
    #: 0 désactive le verrouillage.
    idle_timeout_minutes: int = Field(default=15, alias="ORCHESTRATOR_IDLE_TIMEOUT_MINUTES")
    #: Durée d'une session « gardée ouverte », sans verrouillage par
    #: inactivité. 0 retire l'option de l'écran de connexion.
    remember_me_days: int = Field(default=14, alias="ORCHESTRATOR_REMEMBER_ME_DAYS")
    #: Validité d'une confirmation de mot de passe, comme sudo.
    sudo_minutes: int = Field(default=10, alias="ORCHESTRATOR_SUDO_MINUTES")
    login_lockout_threshold: int = Field(default=5, alias="ORCHESTRATOR_LOGIN_LOCKOUT_THRESHOLD")
    login_lockout_minutes: int = Field(default=15, alias="ORCHESTRATOR_LOGIN_LOCKOUT_MINUTES")
    #: Limite par adresse (format slowapi), complémentaire du verrouillage par
    #: compte : celui-ci ne freine pas un mot de passe essayé sur cent comptes.
    login_rate_limit: str = Field(default="30/minute", alias="ORCHESTRATOR_LOGIN_RATE_LIMIT")

    # --- Politique de mot de passe ---
    password_min_length: int = Field(default=12, alias="ORCHESTRATOR_PASSWORD_MIN_LENGTH")

    # --- État local de l'instance ---
    #: Chemin absolu, résolu une seule fois : un chemin relatif ferait générer
    #: de nouvelles clés selon le répertoire de lancement, et rendrait les
    #: secrets déjà stockés indéchiffrables.
    local_data_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "local_data",
        alias="ORCHESTRATOR_LOCAL_DATA_DIR",
    )

    # --- Documentation / Swagger ---
    #: À désactiver en production : /docs et /redoc exposent toute l'API.
    enable_swagger: bool = Field(default=True, alias="ORCHESTRATOR_ENABLE_SWAGGER")

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if level not in allowed:
            raise ValueError(f"LOG_LEVEL invalide : {value!r}. Attendu l'un de {sorted(allowed)}.")
        return level

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def database_url_from_env(self) -> Optional[str]:
        """URL PostgreSQL si et seulement si DB_HOST est fourni ; None sinon."""
        if not self.db_host:
            return None
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instance unique, construite au premier appel : un test peut ajuster
    l'environnement puis appeler `get_settings.cache_clear()`."""
    return Settings()
