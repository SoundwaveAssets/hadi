# =============================================================================
#  Interface web de l'Orchestrateur CI/CD
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
RUN npm ci

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
