# Hadi : Interface web

Tableau de bord d'administration et de supervision de Hadi (Next.js 16 / React 19 / Tailwind 4). Voir le [README racine](../README.md) pour la présentation générale et le démarrage complet.

## Démarrage

```bash
npm install
npm run dev
```

L'API (`orchestrator_api/`) doit déjà tourner sur `localhost:8000` : le serveur de développement relaie `/api` vers elle. Pour une autre adresse, `API_PROXY_TARGET=http://hote:port npm run dev`.

## Scripts

| Commande | Rôle |
|---|---|
| `npm run dev` | Serveur de développement |
| `npm run build` | Build de production (sortie `standalone`) |
| `npm run start` | Sert le build de production |
| `npm run lint` | ESLint |

## Structure

```
app/dashboard/         Pages de l'interface authentifiée, une route par module
components/devtools/   StatusIcon, PipelineView, LogConsole, DataGrid, ActivityHeatmap
components/ui/         Boutons, champs, modales, cartes
contexts/              Authentification, thème, modules actifs
lib/                   Client API et utilitaires
```

Aucune dépendance de graphiques : les visualisations sont en SVG natif. Aucune police téléchargée : piles système uniquement.
