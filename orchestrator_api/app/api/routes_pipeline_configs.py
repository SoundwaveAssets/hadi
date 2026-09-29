from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from app.core.crypto import secret_box
from app.core.database import get_session
from app.core.deps import require_module, require_roles
from app.models.config import ToolConfig
from app.models.pipeline_config import PipelineConfig
from app.models.user import User, UserRole
from app.providers import PROVIDERS
from app.services import admin_audit
from app.services.argocd_client import ArgoCDClient
from app.services.jenkins_client import JenkinsClient
from app.services.pipeline_config import resolve_argocd_app, resolve_jenkins_job, resolve_sonarqube_key
from app.services.scaffold import generate_application_yaml, generate_jenkinsfile
from app.services.sonarqube_client import SonarQubeClient

router = APIRouter(dependencies=[Depends(require_module("pipelines"))])

_ALLOWED_ROLES = (UserRole.ADMIN, UserRole.SECURITY_OFFICER)


# Schéma d'entrée distinct du modèle de table : SQLModel ne valide pas les
# modèles `table=True`, et ces champs finissent dans des URL Jenkins, un
# Jenkinsfile, un nom d'application Argo CD et un chemin d'API de forge.
_NAME = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"
_PATH = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$"


class PipelineConfigInput(BaseModel):
    repository: str = Field(pattern=_NAME)
    vcs_provider: str = "gitea"
    is_active: bool = True
    webhook_secret: Optional[str] = Field(default=None, min_length=16, max_length=256)
    jenkins_job_name: Optional[str] = Field(default=None, pattern=_NAME)
    sonarqube_project_key: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9:._-]{1,100}$")
    argocd_app_name: Optional[str] = Field(default=None, pattern=r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
    docker_image_name: Optional[str] = Field(default=None, pattern=_PATH)
    git_repo_url: Optional[str] = Field(default=None, max_length=500)
    git_branch: Optional[str] = Field(default=None, pattern=_PATH)
    manifest_path: Optional[str] = Field(default=None, pattern=_PATH)
    jenkins_credentials_id: Optional[str] = Field(default=None, max_length=200)
    k8s_namespace: Optional[str] = Field(default=None, pattern=r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
    auto_create_sonarqube_project: bool = False
    auto_create_jenkins_job: bool = False
    auto_create_argocd_app: bool = False
    #: None = hérite du réglage global (voir domain/decision.py, SecurityCriterion).
    security_criterion: Optional[Literal["new_code", "quality_gate", "total"]] = None
    anomaly_review_threshold: Optional[float] = Field(default=None, ge=0, le=1)
    anomaly_block_threshold: Optional[float] = Field(default=None, ge=0, le=1)
    ai_observation_mode: Optional[bool] = None
    decision_engine_enabled: bool = True

    @field_validator("vcs_provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        if value not in PROVIDERS:
            raise ValueError(f"forge inconnue : {value}")
        return value

    @field_validator("manifest_path", "git_branch", "docker_image_name")
    @classmethod
    def _no_traversal(cls, value: Optional[str]) -> Optional[str]:
        if value and ".." in value:
            raise ValueError("chemin invalide")
        return value

    @field_validator("git_repo_url")
    @classmethod
    def _repo_url(cls, value: Optional[str]) -> Optional[str]:
        if value and not (value.startswith(("http://", "https://", "ssh://", "git@"))):
            raise ValueError("URL de dépôt invalide")
        return value


def _masked(config: PipelineConfig) -> dict:
    """Le secret webhook n'est jamais renvoyé en clair, seulement s'il est configuré."""
    data = config.model_dump()
    data["webhook_secret"] = bool(data.get("webhook_secret"))
    return data


@router.get("")
def list_pipeline_configs(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    configs = db.exec(select(PipelineConfig).order_by(PipelineConfig.created_at.desc())).all()  # type: ignore[arg-type]
    return [_masked(c) for c in configs]


async def _auto_provision(db: Session, config: PipelineConfig) -> list[str]:
    """
    Best-effort : crée ce qui a été demandé côté SonarQube/Jenkins/Argo CD
    pour ce pipeline. N'importe laquelle de ces trois intégrations peut être
    non configurée ou temporairement injoignable, chaque échec devient un
    avertissement renvoyé à l'appelant, jamais une raison de refuser
    l'enregistrement du pipeline lui-même (qui, lui, a déjà réussi).
    """
    warnings: list[str] = []

    if config.auto_create_sonarqube_project:
        try:
            sonar = SonarQubeClient(db)
            key = resolve_sonarqube_key(config, config.repository)
            await sonar.ensure_project(key, name=config.repository)
        except Exception as e:
            warnings.append(f"Projet SonarQube non créé automatiquement : {e}")

    if config.auto_create_jenkins_job:
        if not config.git_repo_url:
            warnings.append("Job Jenkins non créé : l'URL du dépôt Git est requise pour l'auto-création.")
        else:
            try:
                jenkins = JenkinsClient(db)
                job_name = resolve_jenkins_job(config, config.repository)
                await jenkins.create_or_update_pipeline_job(
                    job_name=job_name,
                    git_repo_url=config.git_repo_url,
                    credentials_id=config.jenkins_credentials_id,
                    description=f"Créé automatiquement par Hadi pour le pipeline '{config.repository}'.",
                )
            except Exception as e:
                warnings.append(f"Job Jenkins non créé automatiquement : {e}")

    if config.auto_create_argocd_app:
        if not config.git_repo_url:
            warnings.append("Application Argo CD non créée : l'URL du dépôt Git est requise pour l'auto-création.")
        else:
            try:
                argocd = ArgoCDClient(db)
                app_name = resolve_argocd_app(config, config.repository)
                await argocd.create_application(
                    app_name=app_name,
                    repo_url=config.git_repo_url,
                    namespace=config.k8s_namespace or "default",
                )
            except Exception as e:
                warnings.append(f"Application Argo CD non créée automatiquement : {e}")

    return warnings


@router.post("")
async def create_pipeline_config(
    payload: PipelineConfigInput,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    existing = db.exec(select(PipelineConfig).where(PipelineConfig.repository == payload.repository)).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Le dépôt '{payload.repository}' est déjà enregistré.")
    if not payload.webhook_secret:
        raise HTTPException(status_code=400, detail="Le secret du Webhook est obligatoire : la même valeur que celle saisie sur la forge.")

    config = PipelineConfig(**payload.model_dump(), created_by=user.username)
    config.webhook_secret = secret_box.encrypt(payload.webhook_secret)
    db.add(config)
    db.flush()
    admin_audit.record(
        db, user, "pipeline.create", target_type="pipeline", target_id=config.id, target_label=config.repository,
        after=payload.model_dump(), request=request,
    )
    db.refresh(config)

    warnings = await _auto_provision(db, config)

    return {**_masked(config), "warnings": warnings}


@router.patch("/{config_id}")
def update_pipeline_config(
    config_id: int,
    payload: PipelineConfigInput,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    existing = db.get(PipelineConfig, config_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")

    updates = payload.model_dump(exclude_unset=True, exclude={"repository"})
    if updates.get("webhook_secret"):
        updates["webhook_secret"] = secret_box.encrypt(updates["webhook_secret"])
    else:
        # Champ vide envoyé volontairement (formulaire masqué) : on ne
        # l'écrase pas, même logique que les autres secrets de l'app.
        updates.pop("webhook_secret", None)

    before, after = admin_audit.diff(admin_audit.snapshot(existing, *updates), updates)
    for key, value in updates.items():
        setattr(existing, key, value)
    db.add(existing)
    admin_audit.record(
        db, user, "pipeline.update", target_type="pipeline", target_id=existing.id, target_label=existing.repository,
        before=before, after=after, request=request,
    )
    db.refresh(existing)
    return _masked(existing)


@router.get("/{config_id}/jenkinsfile")
def download_jenkinsfile(
    config_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    """Jenkinsfile de départ pour ce pipeline, voir services/scaffold.py."""
    config = db.get(PipelineConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    tool_config = db.exec(select(ToolConfig).where(ToolConfig.id == 1)).first()
    content = generate_jenkinsfile(config, sonarqube_url=tool_config.sonarqube_url if tool_config else None)
    return PlainTextResponse(
        content,
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="Jenkinsfile"'},
    )


@router.get("/{config_id}/application-yaml")
def download_application_yaml(
    config_id: int,
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    """Manifeste Kubernetes de départ pour ce pipeline, voir services/scaffold.py."""
    config = db.get(PipelineConfig, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    content = generate_application_yaml(config)
    return PlainTextResponse(
        content,
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="application.yaml"'},
    )


@router.delete("/{config_id}")
def delete_pipeline_config(
    config_id: int,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(*_ALLOWED_ROLES)),
):
    existing = db.get(PipelineConfig, config_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    repository = existing.repository
    db.delete(existing)
    admin_audit.record(db, user, "pipeline.delete", target_type="pipeline", target_id=config_id, target_label=repository, request=request)
    return {"status": "success"}
