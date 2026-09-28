from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.config import get_settings
from app.core.crypto import secret_box
from app.core.database import db_manager, get_session
from app.core.deps import require_module, require_password_confirmation, require_roles
from app.models.config import ToolConfig
from app.models.user import User, UserRole
from app.providers import PROVIDERS
from app.services import admin_audit
from app.services.integrations import integrations_health, same_origin, test_tool
from app.services.jenkins_client import JenkinsClient

router = APIRouter()

# Champs chiffrés en base : jamais renvoyés en clair par l'API une fois saisis,
# uniquement leur statut "configuré / non configuré".
_SECRET_FIELDS = {
    "gitea_token",
    "github_token",
    "gitlab_token",
    "jenkins_token",
    "sonarqube_token",
    "argocd_token",
}


def _to_masked_dict(config: ToolConfig) -> dict:
    data = config.model_dump()
    for field in _SECRET_FIELDS:
        data[field] = bool(data.get(field))
    return data


def _get_or_create_config(db: Session) -> ToolConfig:
    config = db.exec(select(ToolConfig).where(ToolConfig.id == 1)).first()
    if not config:
        config = ToolConfig(id=1)
    return config


def _resolve_saved_secret(db: Session, field: str) -> str | None:
    """Déchiffre un champ secret déjà sauvegardé en base, ou None si absent/vide."""
    config = db.exec(select(ToolConfig).where(ToolConfig.id == 1)).first()
    raw = getattr(config, field, None) if config else None
    if not raw:
        return None
    try:
        return secret_box.decrypt(raw)
    except Exception:
        return None


def _resolve_saved_field(db: Session, field: str) -> str | None:
    config = db.exec(select(ToolConfig).where(ToolConfig.id == 1)).first()
    return getattr(config, field, None) if config else None


@router.get("")
def get_config(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    """Récupère la configuration actuelle des outils (secrets masqués)."""
    config = db.exec(select(ToolConfig).where(ToolConfig.id == 1)).first()
    if not config:
        return {}
    return _to_masked_dict(config)


@router.post("")
def save_config(
    config_data: ToolConfig,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    """Crée ou met à jour la configuration (ligne unique id=1). Chiffre les champs sensibles."""
    existing_config = db.exec(select(ToolConfig).where(ToolConfig.id == 1)).first()
    payload = config_data.model_dump(exclude_unset=True, exclude={"id"})
    before = {key: getattr(existing_config, key, None) for key in payload}

    for field in _SECRET_FIELDS:
        if payload.get(field):
            payload[field] = secret_box.encrypt(payload[field])
        elif field in payload:
            # Champ vide envoyé volontairement : on ne l'écrase pas avec du vide
            # si la valeur existante est déjà configurée (évite d'effacer un
            # secret par erreur quand le frontend renvoie le formulaire masqué).
            payload.pop(field)

    if existing_config:
        for key, value in payload.items():
            setattr(existing_config, key, value)
        db.add(existing_config)
    else:
        payload["id"] = 1
        db.add(ToolConfig(**payload))

    before, after = admin_audit.diff(before, {key: value for key, value in payload.items() if key != "id"})
    admin_audit.record(db, user, "settings.save", target_type="settings", before=before, after=after, request=request)
    return {"status": "success", "message": "Configuration sauvegardée avec succès"}


# Chaque outil se sauvegarde séparément, sans toucher aux champs des autres.
# Modèles Pydantic plutôt que la table SQLModel : explicites sur ce que cette
# route peut modifier.
class JenkinsPayload(BaseModel):
    url: str
    user: str | None = None
    token: str | None = None


class SimpleToolPayload(BaseModel):
    url: str
    token: str | None = None


def _record_integration(db: Session, user: User, tool: str, before: dict, after: dict, request: Request) -> None:
    before, after = admin_audit.diff(before, after)
    admin_audit.record(db, user, "integration.save", target_type="integration", target_id=tool, before=before, after=after, request=request)


def _save_simple_tool(db: Session, user: User, tool: str, payload: SimpleToolPayload, request: Request) -> dict:
    """Outils à URL + jeton (SonarQube, Argo CD, forges) : mêmes colonnes `<outil>_url` / `<outil>_token` pour tous."""
    config = _get_or_create_config(db)
    fields = (f"{tool}_url", f"{tool}_token")
    before = admin_audit.snapshot(config, *fields)
    setattr(config, fields[0], payload.url or None)
    if payload.token:
        setattr(config, fields[1], secret_box.encrypt(payload.token))
    db.add(config)
    _record_integration(db, user, tool, before, admin_audit.snapshot(config, *fields), request)
    return {"status": "success"}


@router.post("/jenkins")
def save_jenkins_config(
    payload: JenkinsPayload,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    config = _get_or_create_config(db)
    fields = ("jenkins_url", "jenkins_user", "jenkins_token")
    before = admin_audit.snapshot(config, *fields)
    config.jenkins_url = payload.url
    config.jenkins_user = payload.user
    if payload.token:
        config.jenkins_token = secret_box.encrypt(payload.token)
    db.add(config)
    _record_integration(db, user, "jenkins", before, admin_audit.snapshot(config, *fields), request)
    return {"status": "success"}


@router.get("/jenkins/credentials")
async def list_jenkins_credentials(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    """
    Identifiants des credentials déjà enregistrés dans Jenkins (jamais les
    secrets eux-mêmes), alimente le menu déroulant du formulaire
    d'enregistrement d'un pipeline (voir routes_pipeline_configs.py), pour
    ne pas avoir à taper un identifiant à la main.
    """
    try:
        jenkins = JenkinsClient(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="La configuration de Jenkins est manquante.") from e
    return await jenkins.list_credentials()


@router.post("/sonarqube")
def save_sonarqube_config(
    payload: SimpleToolPayload,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    return _save_simple_tool(db, user, "sonarqube", payload, request)


@router.post("/forge/{kind}")
def save_forge_config(
    kind: str,
    payload: SimpleToolPayload,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    """Jeton d'écriture GitOps d'une forge (voir app/providers/). Le secret de Webhook, lui, reste par pipeline."""
    if kind not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Forge inconnue.")
    return _save_simple_tool(db, user, kind, payload, request)


@router.post("/argocd")
def save_argocd_config(
    payload: SimpleToolPayload,
    request: Request,
    db: Session = Depends(get_session),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    return _save_simple_tool(db, user, "argocd", payload, request)


@router.get("/anomaly-scores")
def list_anomaly_scores(
    limit: int = Query(default=1000, ge=10, le=5000),
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    """
    Derniers scores d'anomalie réellement calculés, pour situer les seuils
    dans la distribution.

    Les pushs sans historique suffisant sont exclus : ils portent un score
    neutre de 0 (voir ai/infer.py, cold start) qui n'est pas une mesure. Les
    laisser empilait une barre à 0 % qui écrasait tout le reste et donnait à
    lire une population normale là où il n'y avait aucune mesure. Ils sont
    comptés à part pour que le nombre reste visible.
    """
    from app.models.audit import AuditLog

    cold_start = AuditLog.ai_explanation.contains("Historique insuffisant")  # type: ignore[union-attr]
    rows = db.exec(
        select(AuditLog.ai_anomaly_score)
        .where(AuditLog.ai_anomaly_score.is_not(None), ~cold_start)  # type: ignore[union-attr]
        .order_by(AuditLog.id.desc())  # type: ignore[arg-type]
        .limit(limit)
    ).all()
    unscored = db.exec(select(func.count()).select_from(AuditLog).where(cold_start)).one()
    return {"scores": [round(float(v), 3) for v in rows], "unscored": unscored}


# --- Connexion PostgreSQL, modifiable après l'installation ---
# Le wizard ne couvre que la toute première configuration ; ces deux routes
# permettent de la faire évoluer ensuite (ex: migration vers un serveur
# PostgreSQL différent) sans avoir à réinstaller.
class DatabaseSettingsPayload(BaseModel):
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str


@router.get("/database")
def get_database_settings(_: User = Depends(require_roles(UserRole.ADMIN))):
    """Paramètres de connexion actifs, jamais le mot de passe."""
    from app.core.database import database_chosen_by_admin

    choisie = database_chosen_by_admin()
    return {
        **(db_manager.current_params or {}),
        #: Une base distante a été choisie ici, et elle l'emporte sur l'environnement.
        "chosen_by_admin": choisie,
        #: L'environnement propose une base : on peut donc y revenir.
        "environment_available": bool(get_settings().database_url_from_env),
    }


@router.post("/database")
def update_database_settings(
    payload: DatabaseSettingsPayload,
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN)),
    _: User = Depends(require_password_confirmation),
):
    """
    Change la connexion PostgreSQL. Teste la nouvelle connexion avant de
    basculer : `connect_and_init` ne remplace l'engine actif qu'après avoir
    confirmé que la nouvelle connexion s'établit, en cas d'échec, cette
    instance continue de tourner sur son ancienne connexion, elle n'est
    jamais laissée sans base fonctionnelle.
    """
    try:
        db_manager.connect_and_init(
            host=payload.db_host,
            port=payload.db_port,
            user=payload.db_user,
            password=payload.db_password,
            dbname=payload.db_name,
            chosen_by_admin=True,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Échec de la connexion : vérifiez l'hôte, le port, l'utilisateur et le mot de passe.",
        ) from e
    # Journalisé dans la NOUVELLE base : c'est elle qui porte désormais l'historique.
    with Session(db_manager.engine) as db:
        admin_audit.record(
            db, user, "database.update", target_type="database",
            after=payload.model_dump(exclude={"db_password"}), request=request,
        )
    return {"status": "success", "message": "Connexion à la base de données mise à jour."}


@router.delete("/database")
def revert_database_settings(
    request: Request,
    user: User = Depends(require_roles(UserRole.ADMIN)),
    _: User = Depends(require_password_confirmation),
):
    """
    Revient à la base fournie par l'environnement, celle de la pile. Le
    fichier local est retiré, la connexion rouverte immédiatement : une
    instance ne reste jamais sans base le temps d'un redémarrage.
    """
    from app.core.database import BOOTSTRAP_FILE

    settings = get_settings()
    if not settings.database_url_from_env:
        raise HTTPException(
            status_code=409,
            detail="Aucune base fournie par l'environnement : renseignez DB_HOST pour pouvoir y revenir.",
        )

    ancien = BOOTSTRAP_FILE.read_bytes() if BOOTSTRAP_FILE.exists() else None
    BOOTSTRAP_FILE.unlink(missing_ok=True)
    try:
        db_manager.engine = None
        db_manager.connect_and_init(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            dbname=settings.db_name,
            persist=False,
        )
    except Exception as e:
        if ancien is not None:
            BOOTSTRAP_FILE.write_bytes(ancien)
        raise HTTPException(status_code=400, detail="La base de l'environnement est injoignable : rien n'a été changé.") from e

    with Session(db_manager.engine) as db:
        admin_audit.record(db, user, "database.revert", target_type="database", request=request)
    return {"status": "success", "message": "Connexion revenue à la base de l'environnement."}


class ToolTestPayload(BaseModel):
    url: str
    user: str | None = None
    token: str | None = None


@router.post("/test/{tool}", dependencies=[Depends(require_module("integrations"))])
async def test_tool_connection(
    tool: str,
    payload: ToolTestPayload,
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    """
    Teste les identifiants tels que saisis (même non sauvegardés). Champ
    jeton vide : repli sur le jeton enregistré, sinon "Tester" échouerait
    toujours après un rechargement de la page, le champ n'étant jamais
    renvoyé en clair.
    """
    # Le secret sauvegardé n'est réutilisé que vers l'hôte pour lequel il a
    # été saisi : sinon, "Tester" avec une URL libre l'enverrait à n'importe
    # quel serveur, celui d'un responsable sécurité indélicat compris.
    saved_url = _resolve_saved_field(db, f"{tool}_url")
    same_host = same_origin(payload.url, saved_url)
    token = payload.token or (_resolve_saved_secret(db, f"{tool}_token") if same_host else None)
    user = payload.user or (_resolve_saved_field(db, "jenkins_user") if tool == "jenkins" and same_host else None)

    try:
        return await test_tool(tool, payload.url, user, token)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail="Outil inconnu (le Moteur IA est une bibliothèque interne : rien à tester ici).",
        ) from e


@router.get("/health")
async def get_integrations_health(
    db: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.SECURITY_OFFICER)),
):
    """Atteignabilité de chaque outil intégré, pour Intégrations et Monitoring (voir services/integrations.py)."""
    return await integrations_health(db)
