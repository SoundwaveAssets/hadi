# Guide de contribution

Merci de votre intérêt pour Hadi. Ce guide explique comment configurer l'environnement de développement, les conventions du projet, et comment soumettre une contribution.

## Code de conduite

Ce projet adhère au [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). En contribuant, vous acceptez de respecter ses termes. Les comportements inacceptables peuvent être signalés à l'adresse indiquée dans le profil GitHub du mainteneur.

## Avant de commencer

- Vérifiez que votre idée n'est pas déjà couverte par une issue ou une PR ouverte.
- Pour les changements importants (nouvelle intégration, refactoring majeur, nouvelle fonctionnalité), ouvrez d'abord une issue pour en discuter.
- Pour les corrections de bugs ou les améliorations mineures, une PR directe est bienvenue.

## Environnement de développement

### Prérequis

- Python 3.11 ou 3.12 (pas 3.13 : voir `requirements.txt`)
- Node.js 20+
- Docker et Docker Compose (pour la pile complète)
- `make` (optionnel, raccourcis disponibles)

### Installation

```bash
# Cloner le dépôt
git clone https://github.com/<votre-fork>/hadi.git
cd hadi

# Installer les dépendances (API + interface)
make install

# Ou manuellement :
cd orchestrator_api && pip install -r requirements.txt && pip install pytest pytest-cov ruff
cd ../frontend && npm ci
```

### Démarrage en développement

```bash
# Pile complète (recommandé pour tester les intégrations)
docker compose up

# Ou séparément (rechargement à chaud)
make dev-api   # API sur :8000
make dev-web   # Interface sur :3000
```

### Variables d'environnement de développement

Créez un fichier `.env` à la racine (copié depuis `.env.example` si disponible) :

```env
LOG_LEVEL=DEBUG
LOG_FORMAT=text
ORCHESTRATOR_ENABLE_SWAGGER=true
```

## Conventions

### Structure du code

```
orchestrator_api/app/
├── domain/        # Règles pures, SANS I/O. Testables sans infrastructure.
├── providers/     # Forges (Gitea, GitHub, GitLab) derrière un contrat commun.
├── services/      # Clients Jenkins, SonarQube, Argo CD.
├── orchestration/ # Flows et jobs de la file de travail.
├── api/           # Routes FastAPI.
├── core/          # Utilitaires transversaux (auth, crypto, DB).
└── models/        # Modèles SQLModel.
```

**Règle fondamentale** : `app/domain/` n'importe jamais FastAPI, SQLModel, httpx, ni aucune bibliothèque d'infrastructure. Toute règle métier qui en dépend appartient à `app/services/` ou `app/orchestration/`.

### Style

- **Python** : `ruff` pour le lint et le formatage. Lancez `make lint-api` avant de soumettre.
- **TypeScript/React** : ESLint. Lancez `make lint-web`.
- Les commentaires et les messages de commit sont en **français** (cohérence avec le projet existant).
- Les noms de variables, fonctions et classes sont en **anglais** (convention Python/JS).

### Commits

Format : `<type>: <description courte en français>`

Types : `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `security`

Exemples :
```
feat: ajouter le support Bitbucket comme forge VCS
fix: corriger la vérification de signature webhook Gitea
security: chiffrer ai_profiles.json avec secret_box
test: couvrir le cas cold-start du moteur d'anomalies
```

## Tests

```bash
# Lancer toute la suite (sans PostgreSQL ni services externes)
make test

# Avec rapport de couverture
cd orchestrator_api && pytest --cov=app --cov-report=term-missing

# Un test précis
cd orchestrator_api && pytest tests/test_decision.py -v
```

### Règles pour les tests

- **Toute modification d'une règle dans `app/domain/`** doit s'accompagner d'un test dans `orchestrator_api/tests/`.
- Les tests ne doivent pas ouvrir de connexion réseau, ni lire de fichiers hors de `tmp_path`.
- Les tests HTTP utilisent SQLite en mémoire via le fixture `client` de `conftest.py`.
- La couverture minimale est fixée à **60 %** dans la CI. Toute PR qui la fait descendre sera refusée.

## Ajouter une intégration (forge, scanner, déploiement)

### Nouvelle forge VCS

1. Créer `app/providers/<nom>.py` implémentant `VersionControlProvider` (voir `app/providers/base.py`).
2. Enregistrer dans `app/providers/__init__.py`.
3. Ajouter les champs de configuration dans `ToolConfig` et `PipelineConfig` si nécessaire.
4. Ajouter les tests dans `tests/test_providers.py`.

### Nouveau scanner de sécurité

1. Créer `app/services/<nom>_client.py` avec une interface similaire à `sonarqube_client.py`.
2. Adapter `app/orchestration/tasks.py` pour appeler le nouveau scanner.
3. Le résultat doit toujours retourner `UNVERIFIABLE` en cas d'échec, jamais `0`.

## Soumettre une Pull Request

1. Forkez le dépôt et créez une branche depuis `main` : `git checkout -b feat/ma-fonctionnalite`
2. Faites vos modifications en respectant les conventions ci-dessus.
3. Vérifiez que `make test` et `make lint` passent au vert.
4. Poussez votre branche et ouvrez une PR vers `main`.
5. Décrivez dans la PR : le problème résolu, la solution choisie, et les tests ajoutés.

La CI vérifie automatiquement sur Linux, macOS et Windows. Une PR ne peut être fusionnée que si tous les jobs passent.

## Questions

Ouvrez une issue avec le label `question` pour toute question sur l'architecture ou les conventions.
