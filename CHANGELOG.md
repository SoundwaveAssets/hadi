# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Versionnage Sémantique](https://semver.org/lang/fr/).

---

## [0.1.0] : 2026-09-29

### Ajouté
- **Documentation complète** : le README devient la documentation de référence, diagrammes de séquence, d'états et d'architecture, cycle de vie d'un pipeline, règle de décision et critères de sécurité, moteur comportemental, rôles et permissions, registre des modules, référence de l'API, branchement outil par outil avec les documentations officielles de Jenkins, SonarQube, Argo CD, Gitea, GitHub, GitLab, Kubernetes et PostgreSQL, modèle de sécurité, sauvegarde et restauration, exploitation, dépannage, questions fréquentes et glossaire. Ajout de `CODE_OF_CONDUCT.md`, des modèles d'issue et de pull request.
- **Installation sans compilation** : `docker-compose.yml` référence les images publiées sur GHCR (`ghcr.io/soundwaveassets/hadi-api`, `hadi-web`), publiées en `linux/amd64` et `linux/arm64`, Apple Silicon et serveurs ARM compris (`.github/workflows/release.yml`). La construction depuis les sources passe par `docker-compose.build.yml`. Les images portent un `LABEL org.opencontainers.image.source` vers le dépôt public et sont construites avec `BUILDX_GIT_INFO=false`, pour qu'aucune référence au dépôt d'origine de la construction n'entre dans leur attestation de provenance. La même publication attache à la release les exécutables de la CLI pour Windows, Linux et macOS, chacun avec son empreinte SHA-256.
- **« Garder la session ouverte »** sur l'écran de connexion : session de `ORCHESTRATOR_REMEMBER_ME_DAYS` jours (14 par défaut, `0` retire l'option), sans verrouillage par inactivité. Le choix est journalisé dans la chaîne d'administration.
- **Journal des actions d'administration** : table `admin_events` et seconde chaîne HMAC (même clé, schéma de sceau distinct). Création/modification de compte, réinitialisation de mot de passe, identités de forge, sauvegarde d'intégration, réglages, notifications, bascule de module, politiques de conformité, pipelines enregistrés, connexions réussies/échouées et verrouillages. Secrets masqués (`***`), jamais journalisés en clair. Consultation et vérification via `GET /api/audit/admin-events` et `/verify`, onglet dédié sur la page *Journal d'audit*, commande `hadi admin-events` ; `hadi audit-verify` rejoue désormais les deux chaînes.
- **Empreinte de l'exécutable de la CLI** : `GET /api/cli/checksum` et en-tête `X-Checksum-Sha256` sur le téléchargement, affichée sur la page Profil avec la commande de vérification de la plateforme. Les noms d'artefacts et le calcul (mis en cache par date de modification) vivent dans `app/services/cli_artifacts.py`.
- **Notifications par la file de travail** : tâche `hadi.notification` (5 tentatives, attente exponentielle). `app/services/notifier.py` sépare la préparation du message (lecture en base : module actif, configuration, destinataires) de son envoi (job réessayable, qui relit la configuration au dernier moment). Sans file de travail (développement sans PostgreSQL), l'envoi reste direct.
- **Journaux en ajout seul au niveau de la base** : déclencheur PostgreSQL refusant `UPDATE`, `DELETE` et `TRUNCATE` sur `audit_logs` et `admin_events`. Sans effet sur SQLite (tests). Le README documente le rôle applicatif non propriétaire qui rend la barrière opposable à l'application elle-même.
- **Profils comportementaux en base** : table `developer_profiles` à la place de `local_data/ai_profiles.json`. Plusieurs répliques de l'API partagent le même apprentissage, un conteneur redémarré ne réapprend rien, et la migration importe automatiquement le fichier existant (conservé comme sauvegarde). `app/ai/infer.py` devient une fonction pure, la persistance vit dans `app/ai/store.py`.
- **Identité du pusher** : table `forge_identities` (compte de forge relié à un utilisateur par un administrateur), provenance de l'identité (`mapped`, `forge`, `git-author`) scellée dans l'audit, sceau versionné (`seal_version`).
- **Licence Apache-2.0** : fichier `LICENSE` et `NOTICE` ajoutés. Le projet est désormais juridiquement open source.
- **Expiration des jetons API** : champ `expires_at` sur `ApiToken`, paramètre `expires_in_days` à la création (1–365 jours). Les jetons expirés sont refusés automatiquement sans révocation manuelle.
- **Logs JSON structurés** : variable `LOG_FORMAT=json` pour activer la journalisation JSON (ingestion Loki/Datadog/ELK). `LOG_FORMAT=text` conserve le format lisible en développement.
- **Healthcheck du worker procrastinate** : `/api/health` retourne désormais 503 si le thread de la file de travail est mort, permettant aux sondes Kubernetes/Docker de détecter un process qui répond mais ne traite plus aucun job.
- **Pagination sur `/api/decisions/pipelines`** : paramètres `limit` (max 200) et `offset`. La réponse inclut `total`, `limit`, `offset`, `items`.
- **Validation du `commit_hash`** : les routes `/gate/{repository}/{commit_hash}` et `/history/{commit_hash}` valident désormais le format (7–64 caractères hexadécimaux) pour prévenir les injections.
- **Swagger/ReDoc désactivables** : variable `ORCHESTRATOR_ENABLE_SWAGGER=false` pour désactiver `/docs`, `/redoc` et `/openapi.json` en production.
- **Couverture de tests dans la CI** : `pytest-cov` avec seuil minimum de 60 %, rapport publié sur Codecov.
- **`CONTRIBUTING.md`** : guide de contribution complet (environnement, conventions, tests, PR).
- **`SECURITY.md`** : politique de divulgation responsable, délais de traitement, périmètre.
- **`CHANGELOG.md`** : ce fichier.
- Passerelle de décision CI/CD semi-automatisée (Human-in-the-Loop).
- Support des forges Gitea, GitHub et GitLab derrière un contrat `VersionControlProvider` commun.
- Moteur de décision isolé (`app/domain/decision.py`) : fail-closed, `UNVERIFIABLE` distinct de `0`.
- Journal d'audit HMAC-SHA256 chaîné, clé hors base, point de bascule ancré dans `audit.genesis`.
- Chiffrement Fernet (AES-128) de tous les secrets stockés en base.
- Règle des 4 yeux sur les dérogations.
- File de travail PostgreSQL (`procrastinate`) avec verrou par dépôt.
- Moteur d'anomalies comportementales par développeur (IsolationForest, mode observation par défaut).
- Politiques de conformité : fenêtres de déploiement, dépôts soumis à examen renforcé.
- Module Notifications SMTP.
- Module Rapports & Exports (CSV/PDF).
- Module Jetons API.
- CLI `hadi` (Typer) : `login`, `pipelines`, `watch`, `logs`, `history`, `pending`, `approve`, `request-derogation`, `derogations`, `audit`, `audit-verify`, `repos`, `gate`.
- CI multi-OS (Linux, macOS, Windows) sur Python 3.11 et 3.12.
- Analyse des dépendances (`pip-audit`, `npm audit`) dans la CI.
- Démarrage de la pile complète vérifié en CI (`docker compose up --wait`).
- Assistant d'installation interactif (wizard) avec jeton de setup.
- Migrations Alembic.
- Portabilité 100 % : aucune dépendance système, aucune URL figée dans le bundle client.

### Sécurité
- **Poste laissé sans surveillance** : verrouillage automatique du tableau de bord après inactivité (`ORCHESTRATOR_IDLE_TIMEOUT_MINUTES`, 15 min), durée de session ramenée de 8 h à 2 h et prolongée seulement tant qu'il y a de l'activité (`POST /api/auth/refresh`), et confirmation du mot de passe exigée sur les actions privilégiées, création d'un jeton API, réinitialisation du mot de passe d'un tiers, changement de la connexion à la base. Un jeton de service, qui n'a pas de mot de passe, se voit refuser ces actions.

### Corrigé
- **Connexion à la base modifiable sans effet** : sous Docker, `DB_HOST` l'emportait toujours et la saisie de l'interface était enregistrée puis ignorée. Un choix explicite d'administrateur prime désormais sur l'environnement, avec un bouton pour revenir à la base de la pile. La bascule teste la connexion, applique les migrations et ne laisse jamais l'instance sans base.
- **Première installation impossible sur une base vierge** : `apply_schema` était appelé sans que l'application procrastinate soit ouverte (`AppNotOpen`). L'API mourait au démarrage et redémarrait en boucle. Invisible sur toute base déjà initialisée, donc sur chaque poste de développement.
- **Sonde de vie confondue avec la sonde de disponibilité** : le `HEALTHCHECK` de l'image interrogeait `/api/health`, qui refuse tant que l'assistant n'est pas terminé. Le conteneur restait `unhealthy` à vie et `docker compose up --wait` n'aboutissait jamais. Nouvelle route `/api/health/live`, toujours `200`, et documentation des deux sondes pour Kubernetes.
- **Journalisation éteinte par les migrations** : `fileConfig` d'Alembic désactivait tous les loggers déjà créés. Plus aucun message applicatif après le démarrage, à commencer par le jeton d'installation que la documentation dit d'aller chercher dans les journaux.
- **`DEPLOYED` posé sans conteneur en marche** : la preuve de déploiement lisait `status.summary.images`, qui liste les images *déclarées* par les ressources. Un `Deployment` en `ImagePullBackOff` y figure. La santé de l'application Argo CD est désormais exigée en plus de l'image.
- **Jobs orphelins repris par le chien de garde** : un job laissé en cours par un process arrêté est remis en file, sur le critère du battement de cœur du worker qui le tient et non sur sa durée. Un travail légitimement long n'est jamais interrompu, un worker mort est récupéré en une trentaine de secondes.
- **Certificat auto-signé impossible à accepter** : `truststore` était injecté globalement et remplaçait `ssl.SSLContext` par une classe vérifiant toujours, y compris quand on lui demandait explicitement de ne pas vérifier. Un Argo CD déployé en cluster, le cas de toute installation, était donc injoignable sans échappatoire. L'injection est retirée, les contextes TLS sont passés explicitement, et `ORCHESTRATOR_TLS_SKIP_VERIFY_HOSTS` déclare les hôtes non vérifiés, hôte par hôte. Une erreur de certificat est désormais nommée comme telle au lieu d'« hôte injoignable ».
- **Actions sans interface** : `useRetrigger` et `useRequestDerogation` existaient côté API et CLI mais n'étaient branchés sur aucun écran, relancer un pipeline ou demander une dérogation exigeait un terminal. Les deux boutons figurent sur la fiche d'un pipeline, avec les mêmes règles de rôle que l'API. `RepositorySelector` refaisait sa propre requête au lieu d'utiliser le hook partagé.
- **Santé des intégrations** : le test authentifié recevait l'URL de sonde suffixée au lieu de l'URL de base (faux « ne ressemble pas à Gitea »), et `authenticated` était lu sur une clé jamais renvoyée. Les tuiles annonçaient donc « non authentifié » même avec des identifiants acceptés.
- **Le journal ne prouvait que la décision, jamais l'acte** : le déploiement, réussi ou en échec, écrit désormais une entrée scellée (`DEPLOYED` / `DEPLOY_FAILED`). Le point de contrôle Jenkins ne lit que les verdicts, jamais ces issues.
- **Pipelines figés** : `PENDING` et `DEPLOYING` sont posés avant que le job ne tourne ; un worker arrêté les laissait dans cet état indéfiniment. Un balayage périodique (`ORCHESTRATOR_PIPELINE_STALL_MINUTES`, 2 h par défaut) les repasse en échec avec leur raison. Une attente humaine n'expire jamais.
- **Historique d'exécution effacé à chaque relance** : un re-push ou un `retrigger` remettait `execution_log` et le numéro de build à zéro, supprimant la trace de la tentative précédente. Les exécutions s'empilent maintenant, séparées par un marqueur.
- **Vocabulaire des statuts divergent** : `ANALYSIS_TRIGGER_FAILED` n'existait que dans l'interface et la CLI, aucun code ne l'a jamais posé ; `DEROGATION_REQUESTED` y était classé comme statut de pipeline alors que c'est une décision. Une énumération unique (`app/domain/pipeline_status.py`) fait foi, et un test compare les trois listes à chaque exécution.
- **Téléchargement de la CLI et son empreinte déplacés du Profil** vers une page dédiée *Client en ligne de commande* : le profil ne concerne que le compte de la personne connectée.
- **Secret de Webhook** : bouton « Générer » (tirage `crypto.getRandomValues` dans le navigateur) à la place d'une fonction serveur morte que rien n'appelait.
- **`_describe_connection_error` introuvable** dans l'assistant d'installation : le test de connexion d'un outil injoignable renvoyait 500 au lieu du diagnostic.
- **`PATCH /api/auth/me`** avec un corps vide effaçait l'email (sémantique PUT sur une route PATCH).
- **Connexion non limitée par IP** : le verrouillage par compte ne freinait pas un même mot de passe essayé sur cent comptes. Limite configurable (`ORCHESTRATOR_LOGIN_RATE_LIMIT`).
- **`hadi watch`** ne s'arrêtait jamais sur une attente humaine, et n'avait aucun délai global : un job CI pouvait immobiliser un agent indéfiniment.
- **Importer `app.main` ouvrait la base et jouait les migrations** (effet de bord de `AppStateManager.__init__`).
- **Jetons API hors du journal d'administration** : créer un compte de service `admin` était la seule action privilégiée à ne laisser aucune trace.
- **Santé des intégrations sans identifiants** : une tuile restait verte avec un jeton révoqué ; la vérification rejoue le test authentifié quand un jeton est enregistré.
- **Empreinte de la CLI introuvable en conteneur** (`HADI_CLI_DIST_DIR`), et 32 clés de traduction orphelines retirées des deux dictionnaires.
- **Le Moteur de décision jugeait la sécurité sur la dette totale du projet** : un dépôt traînant d'anciennes vulnérabilités mettait en attente tous ses pushs, y compris ceux qui en corrigeaient. Le critère devient réglable (`security_criterion`, global et par pipeline) et vaut « code neuf » par défaut, conformément au *Clean as You Code* de SonarQube ; les autres valeurs sont `quality_gate` (verdict du Quality Gate, conditions en échec nommées) et `total` (comportement historique, conservé pour les instances déjà installées). Le critère appliqué est scellé dans l'audit (sceau v3). Aucun repli silencieux d'un critère sur un autre : une mesure absente met en attente en le disant.
- **Métriques de code neuf jamais lues** : SonarQube renvoie les `new_*` dans `period`/`periods`, pas dans `value` ; elles étaient donc toutes vues comme absentes.
- **Suivi des étapes en direct** : nouvel endpoint léger `GET /api/decisions/pipelines/{id}/stages` (wfapi seul), sondé toutes les 2 s pendant l'exécution, là où la console Jenkins, parfois volumineuse, garde une cadence de 5 s. Les listes (Exécutions, Décisions, Dérogations, Vue d'ensemble) s'actualisent seules (5 s si un pipeline travaille, 30 s sinon), et un pipeline en attente d'un humain passe à 20 s au lieu de solliciter Jenkins toutes les 5 s indéfiniment.
- **Distribution des scores d'anomalie illisible** : les pushs sans historique suffisant (score neutre 0) écrasaient l'histogramme ; ils sont désormais exclus et comptés à part. Les seuils sont étiquetés sur le graphe, les axes nommés, et l'effet des seuils est écrit en toutes lettres.
- **`hmac.new(...)` dans `security.py`** : remplacement de l'appel incorrect par `hmac.new(key, msg, digestmod)` avec la signature correcte et un commentaire explicatif.
- **Jetons API déjà révoqués** : la route `POST /api/api-tokens/{id}/revoke` retourne désormais 400 si le jeton est déjà révoqué, au lieu de silencieusement écraser `revoked_at`.

### Modifié
- **Assistant d'installation ramené à trois étapes** : prérequis, base de données, récapitulatif. Les intégrations se règlent depuis la page *Intégrations*, où elles restent modifiables et testables, au lieu d'être demandées une fois pour toutes pendant l'installation. Le fil d'étapes devient cliquable et l'étape de la base se passe d'un bouton quand la pile en fournit déjà une.
- **Diagrammes rendus en images** plutôt qu'en blocs Mermaid : l'application mobile de GitHub n'exécute pas le rendu Mermaid et affichait le code brut. Les sources restent dans `.github/diagrammes/` avec la commande pour les régénérer.
- **`python_requires`** dans `cli/pyproject.toml` : contraint à `>=3.11,<3.13` pour refléter l'incompatibilité de `numpy==1.26.4` avec Python 3.13.
- **`LOG_FORMAT`** ajouté dans `docker-compose.yml` avec la valeur par défaut `text`.

---

[0.1.0]: https://github.com/SoundwaveAssets/hadi/releases/tag/v0.1.0
