import { cn } from "@/lib/cn";

/** Le rond de chargement répété tel quel dans une dizaine de pages, un seul endroit à changer désormais. */
export function Spinner({ className }: { className?: string }) {
  return <div className={cn("w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin", className)} />;
}

/** Spinner centré dans son conteneur, le cas d'usage le plus courant (chargement de page/tableau). */
export function CenteredSpinner({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center justify-center py-16", className)}>
      <Spinner />
    </div>
  );
}
