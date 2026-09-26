import type { NextConfig } from "next";

// Le relais /api vers l'API vit dans proxy.ts, résolu à chaque requête (voir ce fichier).
const isDev = process.env.NODE_ENV !== "production";

const nextConfig: NextConfig = {
  // Emporte uniquement les dépendances réellement atteintes au lieu de tout
  // node_modules : image finale de l'ordre de la dizaine de Mo.
  output: "standalone",

  // `next build` écrit par défaut dans le même .next que `next dev` utilise en
  // direct : lancer un build pendant qu'un serveur de développement tourne le
  // casse. NEXT_DIST_DIR permet de construire à côté (CI, essais locaux) sans
  // toucher au dossier du serveur en cours.
  distDir: process.env.NEXT_DIST_DIR || ".next",

  poweredByHeader: false,
  devIndicators: false,

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
          // Ignoré tant que la page est servie en HTTP simple ; actif dès qu'un
          // TLS est placé devant, sans rien changer ici.
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
          {
            // Une seule origine : 'self' suffit pour connect-src. Aucune
            // police distante. 'unsafe-inline' sur script-src reste imposé par
            // Next (scripts inline d'hydratation) tant qu'un nonce par requête
            // n'est pas mis en place via un middleware ; le script de thème,
            // lui, est un fichier servi.
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
              "style-src 'self' 'unsafe-inline'",
              "font-src 'self' data:",
              "img-src 'self' data: blob:",
              "connect-src 'self'",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
