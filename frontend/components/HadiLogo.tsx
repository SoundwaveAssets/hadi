/**
 * Logo Hadi, importé depuis le fichier SVG, jamais redessiné ici.
 *
 * Source unique : `public/hadi.svg` (et sa copie `app/icon.svg`, que Next.js
 * sert automatiquement comme favicon). Pixel-art en `shape-rendering:
 * crispEdges`, donc net à 16 px comme à 512 px. Les couleurs sont celles de
 * l'image d'origine et ne varient jamais selon le thème.
 */
import Image from "next/image";

const RATIO = 19 / 13;

interface HadiLogoProps {
  /** Hauteur en pixels ; la largeur suit le ratio du logo. */
  size?: number;
  className?: string;
}

export function HadiLogo({ size = 24, className }: HadiLogoProps) {
  return (
    <Image
      src="/hadi.svg"
      alt="Hadi"
      width={Math.round(size * RATIO)}
      height={size}
      className={className}
      priority
      unoptimized
    />
  );
}

/** Le logo et le nom, côte à côte, l'en-tête de chaque écran. */
export function HadiWordmark({ size = 22, className }: { size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className ?? ""}`}>
      <HadiLogo size={size} />
      <span className="font-semibold tracking-tight" style={{ fontSize: size * 0.72 }}>
        Hadi
      </span>
    </span>
  );
}
