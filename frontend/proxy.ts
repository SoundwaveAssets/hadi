import { NextResponse, type NextRequest } from "next/server";

/**
 * Relais /api vers l'API, côté serveur Next, résolu À CHAQUE REQUÊTE.
 *
 * Un `rewrites()` dans next.config.ts est figé dans le manifeste au moment du
 * build : la cible suivait alors l'image partout, et la variable
 * API_PROXY_TARGET posée au déploiement (docker-compose) n'avait aucun effet.
 * Ici, elle est lue à l'exécution : une seule image, n'importe quel
 * environnement. Le navigateur, lui, ne voit toujours que /api sur sa propre
 * origine, donc aucune question de CORS.
 */
export function proxy(request: NextRequest) {
  const target = process.env.API_PROXY_TARGET ?? "http://localhost:8000";
  return NextResponse.rewrite(new URL(request.nextUrl.pathname + request.nextUrl.search, target));
}

export const config = { matcher: "/api/:path*" };
