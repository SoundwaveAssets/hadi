/**
 * Conservé pour les pages qui l'importent déjà : délègue à StatusIcon, la
 * « boule » Jenkins qui porte désormais tous les états. Un seul endroit où
 * les libellés et les couleurs vivent, components/devtools/StatusIcon.tsx.
 */
import { StatusIcon } from "@/components/devtools/StatusIcon";

export function StatusBadge({ status }: { status: string }) {
  return <StatusIcon status={status} withLabel className="text-[13px] font-medium" />;
}
