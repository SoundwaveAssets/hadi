"""
Registre des modules activables depuis /dashboard/modules.

Un module désactivé disparaît de la navigation et ses routes propres refusent
l'accès (`app.core.deps.require_module`). Les modules `is_core` ne peuvent
jamais l'être : sans eux, plus personne ne pourrait les réactiver.

Ajouter un module : une entrée ici, puis `Depends(require_module("ma_cle"))`
sur ses routes. La ligne ModuleState est créée au démarrage suivant.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    name: str
    description: str
    category: str
    is_core: bool = False
    default_active: bool = True


MODULES: list[ModuleDefinition] = [
    # --- Socle (jamais désactivable) ---
    ModuleDefinition(
        key="users",
        name="Authentification & Utilisateurs",
        description="Connexion, comptes, rôles et permissions. Indispensable au fonctionnement du Dashboard.",
        category="Socle",
        is_core=True,
    ),
    ModuleDefinition(
        key="configuration",
        name="Configuration système",
        description="Connexion à la base de données, seuils du Moteur de décision, mode du Moteur IA.",
        category="Socle",
        is_core=True,
    ),
    # --- Cœur fonctionnel (désactivable, actif par défaut) ---
    ModuleDefinition(
        key="pipelines",
        name="Pipelines",
        description="Suivi des pushs reçus depuis la forge et de leur analyse.",
        category="CI/CD",
    ),
    ModuleDefinition(
        key="decisions",
        name="Décisions",
        description="File des pipelines en attente de validation et octroi de dérogations.",
        category="CI/CD",
    ),
    ModuleDefinition(
        key="derogations",
        name="Historique des dérogations",
        description="Registre consultable de toutes les dérogations accordées.",
        category="CI/CD",
    ),
    ModuleDefinition(
        key="audit",
        name="Journal d'audit",
        description="Navigateur du journal d'audit inaltérable.",
        category="Sécurité & conformité",
    ),
    ModuleDefinition(
        key="integrations",
        name="Intégrations",
        description="Connexion et tests des outils externes : forge, Jenkins, SonarQube, Argo CD.",
        category="CI/CD",
    ),
    ModuleDefinition(
        key="monitoring",
        name="Monitoring",
        description="Disponibilité des intégrations et intégrité du journal d'audit, en temps réel.",
        category="Sécurité & conformité",
    ),
    # --- Modules optionnels (inactifs par défaut, à activer explicitement) ---
    ModuleDefinition(
        key="notifications",
        name="Notifications & Alertes",
        description="Envoi d'e-mails (SMTP interne) quand un pipeline est bloqué, en attente, ou dérogé.",
        category="Modules additionnels",
        default_active=False,
    ),
    ModuleDefinition(
        key="reports",
        name="Rapports & Exports",
        description="Export CSV/PDF des pipelines et du journal d'audit sur une période donnée.",
        category="Modules additionnels",
        default_active=False,
    ),
    ModuleDefinition(
        key="api_tokens",
        name="Jetons API",
        description="Comptes de service avec jeton révocable, pour l'accès programmatique au-delà du CLI.",
        category="Modules additionnels",
        default_active=False,
    ),
    ModuleDefinition(
        key="compliance_policies",
        name="Politiques de conformité",
        description="Règles personnalisées : fenêtres de déploiement autorisées, dépôts soumis à examen renforcé.",
        category="Modules additionnels",
        default_active=False,
    ),
]

MODULES_BY_KEY: dict[str, ModuleDefinition] = {m.key: m for m in MODULES}
