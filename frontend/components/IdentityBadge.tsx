"use client";

import { GitBranch, ShieldCheck, ShieldQuestion } from "lucide-react";
import type { IdentitySource } from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/cn";

const STYLE: Record<IdentitySource, { icon: typeof ShieldCheck; className: string }> = {
  mapped: { icon: ShieldCheck, className: "text-good" },
  forge: { icon: GitBranch, className: "text-ink-3" },
  "git-author": { icon: ShieldQuestion, className: "text-warning" },
};

/**
 * Qui a poussé, et à quel point on en est sûr : compte relié, compte de
 * forge, ou simple nom d'auteur Git (non vérifié). Les pipelines d'avant
 * cette distinction n'ont pas de provenance : rien n'est affiché.
 */
export function IdentityBadge({ username, source, commitAuthor, className }: { username: string; source: IdentitySource | null; commitAuthor?: string | null; className?: string }) {
  const t = useT();
  const style = source ? STYLE[source] : null;
  const Icon = style?.icon;
  const title = source
    ? [t(`identity.${source}Hint` as MessageKey), commitAuthor && commitAuthor !== username ? t("identity.commitAuthor", { name: commitAuthor }) : null].filter(Boolean).join(" ")
    : undefined;
  return (
    <span className={cn("inline-flex items-center gap-1.5 min-w-0", className)} title={title}>
      <span className="truncate">{username}</span>
      {Icon && <Icon className={cn("w-3.5 h-3.5 flex-shrink-0", style?.className)} aria-label={t(`identity.${source}` as MessageKey)} />}
    </span>
  );
}
