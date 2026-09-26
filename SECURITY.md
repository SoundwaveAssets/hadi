# Politique de sécurité

## Versions supportées

| Version | Support sécurité |
|---------|-----------------|
| `main`  | ✅ Oui           |

Hadi est en développement actif. Seule la branche `main` reçoit des correctifs de sécurité. Les versions antérieures ne sont pas maintenues.

## Signaler une vulnérabilité

**Ne pas ouvrir d'issue publique pour une vulnérabilité de sécurité.**

Les vulnérabilités doivent être signalées de manière confidentielle pour permettre la préparation d'un correctif avant toute divulgation publique.

### Comment signaler

1. **GitHub Security Advisories (recommandé)** : utilisez l'onglet "Security" → "Report a vulnerability" du dépôt GitHub. La communication est chiffrée et privée.

2. **Email** : si vous ne pouvez pas utiliser GitHub, envoyez un email à l'adresse indiquée dans le profil GitHub du mainteneur principal, avec le sujet `[HADI SECURITY] <titre court>`.

### Informations à inclure

- Description de la vulnérabilité et de son impact potentiel
- Étapes de reproduction (proof of concept si possible)
- Versions affectées
- Correctif suggéré (optionnel)

### Délais de traitement

| Étape | Délai cible |
|-------|-------------|
| Accusé de réception | 48 heures |
| Évaluation initiale | 5 jours ouvrés |
| Correctif (critique) | 14 jours |
| Correctif (important) | 30 jours |
| Divulgation publique | Après déploiement du correctif |

### Périmètre

Sont dans le périmètre :
- L'API FastAPI (`orchestrator_api/`)
- Le frontend Next.js (`frontend/`)
- Le CLI (`cli/`)
- La configuration Docker et les scripts de déploiement

Sont hors périmètre :
- Les services tiers configurés par l'utilisateur (Jenkins, SonarQube, Argo CD, Gitea)
- Les vulnérabilités dans les dépendances tierces déjà connues et non corrigées en amont

### Reconnaissance

Les chercheurs qui signalent des vulnérabilités valides seront mentionnés dans le CHANGELOG (sauf demande d'anonymat).

## Bonnes pratiques de déploiement

Avant de déployer Hadi en production, consultez la section **Configuration** du README et assurez-vous de :

- Définir explicitement `ORCHESTRATOR_MASTER_KEY`, `ORCHESTRATOR_JWT_SECRET` et `ORCHESTRATOR_AUDIT_KEY` (ne pas laisser les valeurs générées automatiquement en production multi-instances)
- Désactiver Swagger/ReDoc : `ORCHESTRATOR_ENABLE_SWAGGER=false`
- Activer les logs JSON : `LOG_FORMAT=json`
- Placer l'API derrière un reverse-proxy TLS (nginx, Caddy, Traefik)
- Restreindre `CORS_ALLOWED_ORIGINS` à votre domaine de production
