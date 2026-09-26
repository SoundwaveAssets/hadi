/**
 * Vue en pipeline : les étapes d'un build, enchaînées, avec l'état de chacune.
 *
 * Inspirée de la « Stage View » de Jenkins : une frise horizontale, une case
 * par étape, la durée en donnée technique. La frise s'arrête à la première
 * étape en échec ou interrompue, afficher les suivantes comme si le build
 * avait continué laisserait croire l'inverse de ce qui s'est passé.
 */
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/cn";
import { StatusIcon, stateOf, type CiState } from "./StatusIcon";

export interface Stage {
  name: string;
  status: string;
  durationMs?: number | null;
}

function formatDuration(ms: number | null | undefined): string {
  if (!ms || ms <= 0) return "-";
  const total = Math.round(ms / 1000);
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
}

function truncateAfterFailure(stages: Stage[]): Stage[] {
  const cut = stages.findIndex((s) => {
    const state = stateOf(s.status);
    return state === "failure" || s.status === "ABORTED";
  });
  return cut === -1 ? stages : stages.slice(0, cut + 1);
}

const BAR: Record<CiState, string> = {
  success: "bg-success",
  failure: "bg-failure",
  unstable: "bg-unstable",
  running: "bg-running",
  aborted: "bg-line-2",
};

const CONNECTOR: Record<CiState, string> = {
  success: "bg-success",
  failure: "bg-failure",
  unstable: "bg-unstable",
  running: "bg-line-2",
  aborted: "bg-line-2",
};

interface PipelineViewProps {
  stages: Stage[];
  /** Coupe la frise après le premier échec (par défaut : oui). */
  stopAtFailure?: boolean;
  className?: string;
}

export function PipelineView({ stages, stopAtFailure = true, className }: PipelineViewProps) {
  const t = useT();
  const visible = stopAtFailure ? truncateAfterFailure(stages) : stages;
  if (visible.length === 0) return null;

  return (
    <ol className={cn("flex items-stretch overflow-x-auto pb-1 -mx-1 px-1", className)} aria-label={t("pipeline.stages")}>
      {visible.map((stage, index) => {
        const state = stateOf(stage.status);
        const isRunning = state === "running";
        const isPending = stage.status === "NOT_EXECUTED";
        const isLast = index === visible.length - 1;

        return (
          <li key={`${stage.name}-${index}`} className="flex items-stretch flex-shrink-0">
            <div className="w-36 flex flex-col gap-1.5 rounded border border-line bg-surface px-3 py-2.5">
              <div className="flex items-center gap-2 min-w-0">
                <StatusIcon status={stage.status} size="sm" />
                <span className="text-[12.5px] font-medium text-ink truncate" title={stage.name}>
                  {stage.name}
                </span>
              </div>
              <span className="font-mono text-[11px] text-ink-3 tabular-nums">
                {isRunning ? t("pipeline.running") : isPending ? t("pipeline.pending") : formatDuration(stage.durationMs)}
              </span>
              <div className="h-1 rounded-full bg-surface-2 overflow-hidden">
                {isRunning ? (
                  <div className="h-full w-1/3 rounded-full bg-running animate-[indeterminate_1.2s_ease-in-out_infinite]" />
                ) : isPending ? null : (
                  <div className={cn("h-full w-full rounded-full", BAR[state])} />
                )}
              </div>
            </div>
            {!isLast && (
              <div className="flex items-center w-4" aria-hidden="true">
                <div className={cn("h-px w-full", CONNECTOR[state])} />
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
