from typing import Optional

from sqlmodel import Field, SQLModel


class ToolConfig(SQLModel, table=True):
    """Réglages modifiables depuis l'interface. Ligne unique (id=1)."""

    __tablename__ = "tool_configurations"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Ces jetons servent à l'écriture GitOps : commiter le SHA approuvé dans le
    # manifeste. Le secret de webhook, lui, reste par dépôt.
    gitea_url: Optional[str] = Field(default=None)
    gitea_token: Optional[str] = Field(default=None)
    github_url: Optional[str] = Field(default=None, description="Base de l'API : vide = https://api.github.com")
    github_token: Optional[str] = Field(default=None)
    gitlab_url: Optional[str] = Field(default=None, description="Instance : vide = https://gitlab.com")
    gitlab_token: Optional[str] = Field(default=None)

    # Jenkins (Compilation, appelé par le workflow d'analyse interne)
    jenkins_url: Optional[str] = Field(default=None)
    jenkins_user: Optional[str] = Field(default=None)
    jenkins_token: Optional[str] = Field(default=None)

    # SonarQube (Sécurité du code)
    sonarqube_url: Optional[str] = Field(default=None)
    sonarqube_token: Optional[str] = Field(default=None)
    
    # Argo CD (Déploiement)
    argocd_url: Optional[str] = Field(default=None)
    argocd_token: Optional[str] = Field(default=None)

    # Le moteur comportemental est une bibliothèque interne (app/ai/) : aucune
    # URL ni jeton, seulement son mode de fonctionnement.
    #: Voir domain/decision.py, SecurityCriterion.
    security_criterion: str = Field(default="new_code", description="new_code | quality_gate | total")
    ai_observation_mode: bool = Field(default=True, description="Si True, l'IA audite mais ne bloque pas")

    # Seuils de décision : ajustables par le Responsable sécurité, sans modification du code
    anomaly_review_threshold: float = Field(
        default=0.5, description="Score IA au-delà duquel une dimension isolée déclenche une mise en attente humaine"
    )
    anomaly_block_threshold: float = Field(
        default=0.8, description="Score IA considéré comme une anomalie comportementale critique"
    )