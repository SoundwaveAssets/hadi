"use client";

import { useT, type MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/cn";

export type CiState = "success" | "failure" | "unstable" | "running" | "aborted";

const STATE_OF: Record<string, CiState> = {
  DEPLOYED: "success",
  DEPLOYING: "running",
  PENDING: "running",
  WAITING_HUMAN: "unstable",
  DEROGATION_PENDING: "unstable",
  BLOCKED: "failure",
  DEPLOY_FAILED: "failure",
  ANALYSIS_FAILED: "failure",
  ANALYSIS_TRIGGER_FAILED: "failure",
  AUTO_AUTH: "success",
  DEROGATION: "success",
  DEROGATION_REQUESTED: "unstable",
  REJECTED_INVALID_SIGNATURE: "failure",
  REJECTED_UNREGISTERED_REPOSITORY: "failure",
  SUCCESS: "success",
  FAILED: "failure",
  FAILURE: "failure",
  UNSTABLE: "unstable",
  IN_PROGRESS: "running",
  ABORTED: "aborted",
  NOT_EXECUTED: "aborted",
  active: "success",
  inactive: "aborted",
};

export function stateOf(status: string): CiState {
  return STATE_OF[status] ?? "aborted";
}

const DOT: Record<CiState, string> = {
  success: "bg-success",
  failure: "bg-failure",
  unstable: "bg-unstable",
  running: "bg-running status-running",
  aborted: "bg-aborted",
};


const SIZE = {
  sm: "w-2.5 h-2.5",
  md: "w-3 h-3",
  lg: "w-4 h-4",
} as const;

function useStatusLabel() {
  const t = useT();
  return (status: string) => {
    const key = `status.${status}` as MessageKey;
    const label = t(key);
    return label === key ? status : label;
  };
}

interface StatusIconProps {
  status: string;
  size?: keyof typeof SIZE;
  withLabel?: boolean;
  className?: string;
}

export function StatusIcon({ status, size = "md", withLabel = false, className }: StatusIconProps) {
  const label = useStatusLabel()(status);
  const state = stateOf(status);

  return (
    <span className={cn("inline-flex items-center gap-2 whitespace-nowrap", className)} title={label} role="img" aria-label={label}>
      <span className={cn("inline-block rounded-full flex-shrink-0", SIZE[size], DOT[state])} />
      {withLabel ? <span className="text-ink-2">{label}</span> : <span className="sr-only">{label}</span>}
    </span>
  );
}

export function StatusPill({ status, className }: { status: string; className?: string }) {
  const label = useStatusLabel()(status);
  const state = stateOf(status);
  const tone: Record<CiState, string> = {
    success: "bg-success-soft text-success",
    failure: "bg-failure-soft text-failure",
    unstable: "bg-unstable-soft text-unstable",
    running: "bg-running-soft text-running",
    aborted: "bg-aborted-soft text-ink-2",
  };
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 h-5 rounded text-[11.5px] font-medium whitespace-nowrap", tone[state], className)}>
      <StatusIcon status={status} size="sm" />
      {label}
    </span>
  );
}
