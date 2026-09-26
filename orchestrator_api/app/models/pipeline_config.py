from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class PipelineConfig(SQLModel, table=True):
    """
    Un dépôt suivi. L'application gère plusieurs pipelines indépendants, pas
    un jeu de réglages global appliqué à tout le monde. Un dépôt sans ligne ici est rejeté par le
    webhook : l'enregistrement précède le premier push.

    Les champs de correspondance et de seuils sont optionnels : vides, ils
    retombent sur le nom du dépôt ou sur les réglages globaux (ToolConfig).
    """

    __tablename__ = "pipeline_configs"

    id: Optional[int] = Field(default=None, primary_key=True)
    repository: str = Field(index=True, unique=True, description="Nom exact du dépôt sur la forge (repository.name / project.name du Webhook).")
    # Forge d'origine (gitea, github, gitlab) : fixe le format du webhook,
    # la vérification de signature et l'API d'écriture du manifeste.
    vcs_provider: str = Field(default="gitea")
    is_active: bool = Field(default=True, description="Si faux, le Webhook rejette les push de ce dépôt sans les traiter.")

    # Secret HMAC propre à CE dépôt, jamais un secret global. Chiffré au
    # repos, jamais renvoyé en clair par l'API.
    webhook_secret: str = Field(description="Secret du Webhook de ce dépôt, chiffré.")

    # Correspondance de noms avec les outils externes, vide = identique au nom du dépôt.
    jenkins_job_name: Optional[str] = Field(default=None)
    sonarqube_project_key: Optional[str] = Field(default=None)
    argocd_app_name: Optional[str] = Field(default=None)
    # Image telle qu'elle apparaît dans le manifeste, sans le registre ; vide =
    # nom du dépôt. C'est la ligne `image:` que le déploiement épingle.
    docker_image_name: Optional[str] = Field(default=None)

    # Auto-provisionnement : créer le projet SonarQube, le job Jenkins et
    # l'application Argo CD à l'enregistrement (voir services/scaffold.py).
    # Aucun n'est activé par défaut ; les fichiers restent téléchargeables.
    git_repo_url: Optional[str] = Field(
        default=None, description="URL de clonage du dépôt (ex: http://.../mon-org/mon-projet.git), requis pour l'auto-provisionnement Jenkins/Argo CD."
    )
    jenkins_credentials_id: Optional[str] = Field(
        default=None, description="Identifiant d'un credential Git déjà créé dans Jenkins (vide si dépôt public)."
    )
    k8s_namespace: Optional[str] = Field(default=None, description="Namespace cible pour l'Application Argo CD, vide = 'default'.")
    # Écriture GitOps : le manifeste vit dans le dépôt applicatif, sur la
    # branche que suit Argo CD.
    git_branch: Optional[str] = Field(default=None, description="Branche suivie par Argo CD, vide = 'main'.")
    manifest_path: Optional[str] = Field(default=None, description="Chemin du manifeste dans le dépôt, vide = 'application.yaml'.")
    auto_create_sonarqube_project: bool = Field(default=False)
    auto_create_jenkins_job: bool = Field(default=False)
    auto_create_argocd_app: bool = Field(default=False)

    # Réglages du Moteur de décision propres à ce pipeline, vide = valeur globale (ToolConfig).
    #: None = hérite du réglage global (voir models/config.py).
    security_criterion: Optional[str] = Field(default=None, description="new_code | quality_gate | total")
    anomaly_review_threshold: Optional[float] = Field(default=None)
    anomaly_block_threshold: Optional[float] = Field(default=None)
    ai_observation_mode: Optional[bool] = Field(default=None, description="None = hérite du réglage global.")

    # Bouton d'urgence, par pipeline et sans équivalent global : désactivé, ce
    # dépôt autorise tout. Les preuves restent collectées et tracées, elles ne
    # pèsent plus sur la décision.
    decision_engine_enabled: bool = Field(default=True)

    created_by: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
