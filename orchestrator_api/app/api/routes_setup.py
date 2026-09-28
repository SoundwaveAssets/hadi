from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core import setup_token
from app.core.database import db_manager, get_session
from app.core.state_manager import app_state_manager
from app.models.system import SystemSettings

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
