from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Journalisation configurée avant tout import applicatif (LOG_LEVEL, LOG_FORMAT).
from app.config import get_settings
from app.core.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

from app.api import (  # noqa: E402
    routes_api_tokens,
    routes_audit,
    routes_auth,
    routes_cli,
    routes_compliance_policies,
    routes_config,
    routes_decisions,
    routes_modules,
    routes_notifications,
    routes_pipeline_configs,
    routes_reports,
    routes_setup,
    routes_users,
    routes_webhooks,
)
from app.core.ratelimit import limiter  # noqa: E402
from app.core.state_manager import app_state_manager  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tant que l'assistant n'est pas verrouillé, le jeton d'installation est
    # rappelé au démarrage : c'est là que l'administrateur le cherche.
    from app.core import setup_token
    from app.orchestration.queue import worker

    app_state_manager.refresh()
    if not app_state_manager.state.setup_locked:
        setup_token.announce()
    if app_state_manager.state.db_connected:
        start_queue_worker()
    yield
    worker.stop()


def start_queue_worker() -> None:
    """Démarre la file de travail sur la base connectée (au démarrage, ou à la fin de l'étape base de l'assistant)."""
    from app.core.database import db_manager, resolve_database_url
    from app.orchestration.queue import worker

    url = resolve_database_url() or db_manager.current_url
    if url and db_manager.engine is not None:
        worker.start(url, db_manager.engine, concurrency=settings.worker_concurrency)


app = FastAPI(
    title="Hadi API",
    redirect_slashes=False,
    lifespan=lifespan,
    # Swagger et ReDoc désactivés en production (ORCHESTRATOR_ENABLE_SWAGGER=false).
    # En production, ces interfaces exposent la structure complète de l'API et
    # permettent d'exécuter des requêtes directement depuis le navigateur.
    docs_url="/docs" if settings.enable_swagger else None,
    redoc_url="/redoc" if settings.enable_swagger else None,
    openapi_url="/openapi.json" if settings.enable_swagger else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS : utile seulement quand l'interface n'est pas servie par le relais Next
# (développement sur deux ports). CORS_ALLOWED_ORIGINS, séparées par des virgules.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# En-têtes de sécurité. Pas de CSP : l'API ne sert que du JSON, et /docs
# (Swagger, scripts CDN) casserait avec une CSP stricte.
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Sans effet en HTTP simple, actif dès qu'un TLS est devant.
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response

# Enregistrement des routes
app.include_router(routes_setup.router, prefix="/api/setup", tags=["Setup Wizard"])
app.include_router(routes_auth.router, prefix="/api/auth", tags=["Authentification"])
app.include_router(routes_config.router, prefix="/api/config", tags=["Configuration"])
app.include_router(routes_users.router, prefix="/api/users", tags=["Utilisateurs"])
app.include_router(routes_webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
app.include_router(routes_decisions.router, prefix="/api/decisions", tags=["Decisions"])
app.include_router(routes_audit.router, prefix="/api/audit", tags=["Audit"])
app.include_router(routes_modules.router, prefix="/api/modules", tags=["Modules"])
app.include_router(routes_notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(routes_reports.router, prefix="/api/reports", tags=["Rapports"])
app.include_router(routes_api_tokens.router, prefix="/api/api-tokens", tags=["Jetons API"])
app.include_router(routes_compliance_policies.router, prefix="/api/compliance-policies", tags=["Politiques de conformité"])
app.include_router(routes_pipeline_configs.router, prefix="/api/pipeline-configs", tags=["Pipelines"])
app.include_router(routes_cli.router, prefix="/api/cli", tags=["CLI"])


@app.get("/api/health/live")
async def liveness():
    """Sonde de vie : le processus répond. Toujours 200, quel que soit l'état de l'installation."""
    return {"status": "alive"}


@app.get("/api/health")
async def health_check():
    """
    Sonde de disponibilité : interface, CLI, readinessProbe. Refuse tant que
    l'installation n'est pas terminée ou que le worker de la file est mort.
    """
    from app.orchestration.queue import worker

    app_state_manager.refresh()
    state = app_state_manager.state

    if not state.is_setup_complete:
        raise HTTPException(
            status_code=503,
            detail={"message": "Setup required", "setup_step": state.setup_step if state.db_connected else "database"},
        )

    queue_running = worker.running
    if not queue_running:
        raise HTTPException(
            status_code=503,
            detail={"message": "File de travail indisponible", "queue_worker": False},
        )

    return {
        "status": "ok",
        "message": "API opérationnelle",
        "setup_complete": True,
        "queue_worker": True,
    }
