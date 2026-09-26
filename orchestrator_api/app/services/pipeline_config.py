"""
Résolution des réglages effectifs d'un pipeline (dépôt) : ce qu'il
surcharge explicitement (PipelineConfig), sinon repli sur la convention par
défaut (nom du dépôt tel quel) ou sur le réglage global (ToolConfig) -
centralisé ici pour que webhooks/tasks/decision_engine/compliance
appliquent tous exactement la même règle de repli.
"""
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.models.pipeline_config import PipelineConfig


def get_pipeline_config(session: Session, repository: str) -> PipelineConfig | None:
    return session.exec(select(PipelineConfig).where(PipelineConfig.repository == repository)).first()


def resolve_jenkins_job(config: PipelineConfig | None, repository: str) -> str:
    return config.jenkins_job_name if config and config.jenkins_job_name else repository


def resolve_sonarqube_key(config: PipelineConfig | None, repository: str) -> str:
    return config.sonarqube_project_key if config and config.sonarqube_project_key else repository


def resolve_argocd_app(config: PipelineConfig | None, repository: str) -> str:
    return config.argocd_app_name if config and config.argocd_app_name else repository


def resolve_docker_image(config: PipelineConfig | None, repository: str) -> str:
    return config.docker_image_name if config and config.docker_image_name else repository


def resolve_git_branch(config: PipelineConfig | None) -> str:
    return config.git_branch if config and config.git_branch else "main"


def resolve_manifest_path(config: PipelineConfig | None) -> str:
    return (config.manifest_path if config and config.manifest_path else "application.yaml").lstrip("/")


def parse_repo_slug(git_repo_url: str | None) -> tuple[str, str] | None:
    """
    (propriétaire, dépôt) depuis une URL de clonage Gitea
    (http://forge/org/projet.git ou git@forge:org/projet.git). None si l'URL
    ne se lit pas : l'appelant doit refuser de déployer, pas deviner.
    """
    if not git_repo_url:
        return None
    url = git_repo_url.strip()
    if "://" in url:
        path = urlsplit(url).path
    elif ":" in url:  # forme scp : git@host:owner/repo.git
        path = url.split(":", 1)[1]
    else:
        return None
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[-2], parts[-1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return (owner, repo) if owner and repo else None
