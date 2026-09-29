# =============================================================================
#  Interface web de Hadi
# =============================================================================
# Sert le build de PRODUCTION (`next start`), jamais `next dev` : ce dernier
# expose les source maps de toute l'application et n'est pas prévu pour ça.
ARG NODE_VERSION=22

# -----------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# `npm ci` et non `npm install` : respecte le lockfile à la lettre, donc un
# build reproductible. `npm install` peut mettre à jour des dépendances en
# silence, ce qui est exactement ce qu'un lockfile existe pour empêcher.
#
# Les délais et réessais sont explicites : sur une liaison lente, les valeurs
# par défaut abandonnent en EIDLETIMEOUT et la construction depuis les sources
# échoue alors que rien n'est cassé. `--no-audit` supprime un appel réseau qui
# n'apporte rien à l'image produite : l'audit des dépendances a sa place dans
# la CI, pas dans la construction. Le cache npm survit aux reprises, pour ne
# pas retélécharger l'arbre entier après une coupure.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --fetch-timeout=600000 --fetch-retries=5 --fetch-retry-maxtimeout=120000

# -----------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Aucune variable NEXT_PUBLIC_* n'est injectée ici, volontairement : Next.js
# les fige dans le bundle client au moment du build. Une URL d'API gravée à ce
# moment-là suivrait l'image partout, y compris chez quelqu'un dont l'API n'est
# pas à cette adresse. Le client appelle donc /api en relatif, et le serveur
# Next relaie vers l'API : voir next.config.ts.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# -----------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS web

# Rattache l'image au dépôt public : c'est ce lien que GHCR affiche sur le
# paquet, et la seule source à publier. Le dépôt d'origine de la construction
# est tenu hors de l'image (BUILDX_GIT_INFO=false, voir CONTRIBUTING.md).
LABEL org.opencontainers.image.source="https://github.com/SoundwaveAssets/hadi" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.title="Hadi Web" \
      org.opencontainers.image.description="Passerelle de décision entre le dépôt et la production, interface"

RUN apk add --no-cache curl \
    && addgroup -g 10002 -S nextjs \
    && adduser -u 10002 -S nextjs -G nextjs

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Sortie `standalone` : Next n'emporte que les dépendances réellement
# atteintes, au lieu de tout node_modules. Voir next.config.ts.
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nextjs /app/public ./public

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]
