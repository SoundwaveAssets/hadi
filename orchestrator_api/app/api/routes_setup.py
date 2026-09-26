import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core import setup_token
from app.core.crypto import secret_box
from app.core.database import db_manager, get_session
from app.core.state_manager import app_state_manager
from app.core.tls import context_for
from app.models.config import ToolConfig
from app.models.system import SystemSettings
from app.services.integrations import describe_connection_error

router = APIRouter()


def require_setup_token(x_setup_token: str | None = Header(default=None)) -> None:
    """Toutes les étapes de l'assistant, sauf la lecture du statut."""
    if not setup_token.check(x_setup_token):
        raise HTTPException(status_code=401, detail="Jeton d'installation absent ou invalide : voir les journaux de l'API.")


def _require_step(session: Session, expected_step: str) -> SystemSettings:
    settings = session.exec(select(SystemSettings)).first()
    if not settings:
        raise HTTPException(
            status_code=409,
            detail="Base de données non initialisée. Commencez par l'étape 'database'.",
        )
    if settings.setup_locked:
        raise HTTPException(status_code=409, detail="L'installation est déjà terminée et verrouillée.")
    if settings.setup_step != expected_step:
        raise HTTPException(
            status_code=409,
            detail=f"Étape incorrecte : l'installation en est à '{settings.setup_step}', pas '{expected_step}'.",
        )
    return settings


@router.get("/status")
def get_setup_status():
    """Consommé par le frontend pour savoir sur quelle étape du wizard atterrir."""
    app_state_manager.refresh()
    state = app_state_manager.state
    return {
        "db_connected": state.db_connected,
        "setup_step": state.setup_step if state.db_connected else "database",
        "setup_locked": state.setup_locked,
    }


# --- Étape 1 : Base de données ---
# Pas d'étape "choisir un compte admin" : la connexion à une base fraîche
# sème automatiquement un compte admin/admin (façon SonarQube), à changer
# obligatoirement à la première connexion (voir routes_auth.change_password).
class DatabasePayload(BaseModel):
    db_host: str
    db_port: int = 5432
    db_name: str = "orchestrator_db"
    db_user: str
    db_password: str


@router.post("/database", dependencies=[Depends(require_setup_token)])
def configure_database(payload: DatabasePayload):
    if app_state_manager.state.db_connected and app_state_manager.state.setup_locked:
        raise HTTPException(status_code=409, detail="L'installation est déjà terminée et verrouillée.")

    try:
        db_manager.connect_and_init(
            host=payload.db_host,
            port=payload.db_port,
            user=payload.db_user,
            password=payload.db_password,
            dbname=payload.db_name,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Échec de la connexion à PostgreSQL : vérifiez l'hôte, le port et les identifiants.",
        ) from e

    app_state_manager.refresh()
    from app.main import start_queue_worker  # import tardif : main importe ce module

    start_queue_worker()
    return {"status": "success", "next_step": app_state_manager.state.setup_step}


# --- Étape 2 : Intégrations ---
# Pas de secret de webhook ici : chaque dépôt a le sien, saisi à son
# enregistrement. Le moteur comportemental n'a ni URL ni jeton.
class IntegrationsPayload(BaseModel):
    gitea_url: str | None = None
    gitea_token: str | None = None
    jenkins_url: str | None = None
    jenkins_user: str | None = None
    jenkins_token: str | None = None
    sonarqube_url: str | None = None
    sonarqube_token: str | None = None
    argocd_url: str | None = None
    argocd_token: str | None = None


@router.post("/integrations", dependencies=[Depends(require_setup_token)])
def configure_integrations(payload: IntegrationsPayload, db: Session = Depends(get_session)):
    settings = _require_step(db, "integrations")

    config = db.exec(select(ToolConfig).where(ToolConfig.id == 1)).first() or ToolConfig(id=1)

    config.gitea_url = payload.gitea_url
    config.gitea_token = secret_box.encrypt(payload.gitea_token) if payload.gitea_token else None
    config.jenkins_url = payload.jenkins_url
    config.jenkins_user = payload.jenkins_user
    config.jenkins_token = secret_box.encrypt(payload.jenkins_token)
    config.sonarqube_url = payload.sonarqube_url
    config.sonarqube_token = secret_box.encrypt(payload.sonarqube_token)
    config.argocd_url = payload.argocd_url
    config.argocd_token = secret_box.encrypt(payload.argocd_token)

    db.add(config)
    settings.setup_step = "review"
    db.add(settings)
    db.commit()

    return {"status": "success", "next_step": "review"}


class ConnectionTestPayload(BaseModel):
    url: str


@router.post("/integrations/test/{tool}", dependencies=[Depends(require_setup_token)])
async def test_integration_connection(tool: str, payload: ConnectionTestPayload):
    """
    Ping léger pour rassurer l'admin pendant le wizard (pas une validation
    d'auth : aucun compte n'existe encore à ce stade pour exiger un jeton).

    Fermé dès que l'installation est verrouillée, sans ce garde-fou, cette
    route restait un point de sonde HTTP non authentifié exploitable en SSRF
    indéfiniment après l'installation. Une fois verrouillée, l'équivalent
    authentifié (avec vérification réelle des identifiants) est
    POST /api/config/test/{tool}.
    """
    if app_state_manager.state.setup_locked:
        raise HTTPException(
            status_code=403,
            detail="Installation déjà verrouillée : utilisez POST /api/config/test/{tool} (authentifié) à la place.",
        )
    if tool not in {"gitea", "github", "gitlab", "jenkins", "sonarqube", "argocd"}:
        raise HTTPException(status_code=400, detail="Outil inconnu.")
    try:
        # follow_redirects : certains outils (Argo CD notamment) répondent en
        # clair sur leur port HTTP mais redirigent vers HTTPS par défaut -
        # sans ça, on ne reçoit qu'un 307 sans jamais atteindre l'application.
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True, verify=context_for(payload.url)) as client:
            response = await client.get(payload.url)
        return {"reachable": response.status_code < 500}
    except Exception as e:
        return {"reachable": False, "error": describe_connection_error(payload.url, e)}


# --- Étape 3 : Récapitulatif et verrouillage ---
@router.post("/complete", dependencies=[Depends(require_setup_token)])
def complete_setup(db: Session = Depends(get_session)):
    settings = _require_step(db, "review")
    settings.setup_step = "done"
    settings.setup_locked = True
    db.add(settings)
    db.commit()
    setup_token.discard()

    app_state_manager.refresh()
    return {"status": "success", "message": "Installation terminée et verrouillée."}
