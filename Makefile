# =============================================================================
#  Hadi : commandes de développement
# =============================================================================
# Raccourcis pour le développement local. Rien ici n'est nécessaire pour
# FAIRE TOURNER le projet : `docker compose up` suffit, sur les trois systèmes.
#
# Sous Windows, `make` s'installe via `winget install GnuWin32.Make`,
# `choco install make` ou `scoop install make` : ou passez directement par les
# commandes Docker, identiques partout.

# Détection du binaire Python de la plateforme.
ifeq ($(OS),Windows_NT)
	PYTHON ?= python
else
	PYTHON ?= python3
endif

API_DIR := orchestrator_api
WEB_DIR := frontend

# Nom de l'artefact CLI selon la plateforme courante. PyInstaller ne croise pas
# les compilations : chaque binaire se produit sur la plateforme qu'il vise.
ifeq ($(OS),Windows_NT)
	CLI_ARTIFACT := hadi-windows
else
	UNAME_S := $(shell uname -s)
	ifeq ($(UNAME_S),Darwin)
		CLI_ARTIFACT := hadi-macos
	else
		CLI_ARTIFACT := hadi-linux
	endif
endif

.DEFAULT_GOAL := help
.PHONY: help up down logs restart build test test-api test-cli lint lint-api lint-web install dev-api dev-web clean keys cli-binary migrate

help: ## Afficher cette aide
	@echo "Hadi : commandes disponibles :"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""

# --- Pile complète -----------------------------------------------------------

up: ## Démarrer la pile complète (base + API + interface)
	docker compose up -d --build --wait
	@echo ""
	@echo "  Interface : http://localhost:$${PUBLIC_PORT:-8088}"
	@echo ""

down: ## Arrêter la pile (les volumes sont conservés)
	docker compose down

logs: ## Suivre les journaux de tous les services
	docker compose logs -f

restart: ## Redémarrer la pile
	docker compose restart

build: ## Reconstruire les images sans cache
	docker compose build --no-cache

clean: ## Tout arrêter et SUPPRIMER les volumes (base et clés comprises)
	docker compose down -v

# --- Qualité -----------------------------------------------------------------

test: test-api test-cli ## Lancer toute la suite de tests

test-api: ## Tests de l'API
	cd $(API_DIR) && $(PYTHON) -m pytest

test-cli: ## Tests de la CLI
	cd cli && $(PYTHON) -m pytest -q

lint: lint-api lint-web ## Lancer tous les linters

lint-api: ## Lint de l'API et de la CLI (ruff)
	$(PYTHON) -m ruff check $(API_DIR) cli --config $(API_DIR)/ruff.toml

lint-web: ## Lint de l'interface
	cd $(WEB_DIR) && npm run lint

# --- Développement hors conteneur --------------------------------------------

install: ## Installer les dépendances des deux projets
	cd $(API_DIR) && $(PYTHON) -m pip install -r requirements.txt pytest ruff
	cd $(WEB_DIR) && npm ci

dev-api: ## Lancer l'API en rechargement à chaud
	cd $(API_DIR) && $(PYTHON) -m uvicorn app.main:app --reload

dev-web: ## Lancer l'interface en rechargement à chaud
	cd $(WEB_DIR) && npm run dev

# --- Utilitaires -------------------------------------------------------------

cli-binary: ## Produire l'exécutable autonome de la CLI pour CETTE plateforme
	cd cli && $(PYTHON) -m pip install --quiet pyinstaller \
		&& $(PYTHON) -m PyInstaller --onefile --console --name $(CLI_ARTIFACT) main.py
	@echo ""
	@echo "  Binaire : cli/dist/$(CLI_ARTIFACT)"
	@echo "  Servi par GET /api/cli/download?os=..."
	@echo ""

migrate: ## Créer une migration Alembic depuis les modèles (make migrate m="ajout colonne x")
	cd $(API_DIR) && $(PYTHON) -m alembic revision --autogenerate -m "$(m)"

keys: ## Générer des secrets prêts à coller dans un .env
	@$(PYTHON) -c "from cryptography.fernet import Fernet; print('ORCHESTRATOR_MASTER_KEY=' + Fernet.generate_key().decode())"
	@$(PYTHON) -c "import secrets; print('ORCHESTRATOR_JWT_SECRET=' + secrets.token_urlsafe(48))"
	@$(PYTHON) -c "import secrets; print('ORCHESTRATOR_AUDIT_KEY=' + secrets.token_urlsafe(48))"
