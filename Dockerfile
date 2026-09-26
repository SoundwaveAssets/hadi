# =============================================================================
#  API de l'Orchestrateur CI/CD
# =============================================================================
# Build multi-étages : les outils de compilation (gcc, en-têtes libpq) restent
# dans l'étage `builder` et n'entrent jamais dans l'image finale.
#
# Python 3.12 et non 3.13 : les commentaires de requirements.txt justifient
# plusieurs pins "pour les wheels cp313", mais numpy==1.26.4 ne publie de
# wheels que jusqu'à cp312. Sur 3.13, pip retomberait sur une compilation
# depuis les sources qui échoue. 3.12 est la version la plus récente réellement
# compatible avec l'ensemble des pins actuels.
ARG PYTHON_VERSION=3.12

# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Environnement virtuel dédié : l'étage final n'a plus qu'à le recopier,
# sans rien savoir de la façon dont il a été construit.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY orchestrator_api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS api

# libpq5 seule (bibliothèque d'exécution), pas libpq-dev ni gcc.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Utilisateur non privilégié. Un conteneur qui tourne en root est le premier
# point relevé par tout audit : et il n'y a ici aucune raison d'en avoir besoin.
RUN useradd --create-home --uid 10001 orchestrator

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --chown=orchestrator:orchestrator orchestrator_api/ /app/

# État local de l'instance (clés générées, profils comportementaux). À monter
# en volume : sans persistance, un conteneur recréé régénère ses clés et rend
# illisible tout ce qui est déjà chiffré en base.
RUN mkdir -p /app/local_data && chown orchestrator:orchestrator /app/local_data
VOLUME ["/app/local_data"]

USER orchestrator
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# La file de travail (PostgreSQL, SKIP LOCKED) accepte plusieurs processus :
# chaque worker uvicorn embarque son propre consommateur de jobs.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
