"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, Clock, GitBranch, Layers, ShieldAlert } from "lucide-react";
import { useOverview } from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import { useFormatDate } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { ActivityHeatmap } from "@/components/devtools/ActivityHeatmap";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { CenteredSpinner } from "@/components/ui/Spinner";
import { RepositorySelector } from "@/components/RepositorySelector";
import { useAuth } from "@/contexts/AuthContext";

export default function DashboardPage() {
  const t = useT();
  const { user } = useAuth();
  const fmt = useFormatDate();
  const [repository, setRepository] = useState("");
  const { data, isLoading } = useOverview(repository || undefined);
  const summary = data?.summary ?? null;
  const pipelines = data?.recent ?? [];
  const activity = data?.activity ?? [];

  const statusCounts = summary?.pipeline_status_counts ?? {};
  const waiting = statusCounts.WAITING_HUMAN ?? 0;
  const blocked = statusCounts.BLOCKED ?? 0;
  const deployed = statusCounts.DEPLOYED ?? 0;
  const total = summary?.pipelines_total ?? 0;

  const canAct = user?.role === "admin" || user?.role === "security_officer";
  const needsAttention = waiting + blocked;

  return (
    <div className="space-y-4 ">
      <PageHeader
        title={t("page.overview")}
        actions={<RepositorySelector value={repository} onChange={setRepository} />}
      />

      {isLoading ? (
        <CenteredSpinner className="py-12" />
      ) : (
        <>
          {/* Ligne d'alerte contextuelle : uniquement pour les rôles qui peuvent
              réellement agir, et seulement quand il y a vraiment quelque chose
              à traiter, pas un bandeau vide générique. */}
          {canAct && needsAttention > 0 && (
            <Link
              href="/dashboard/decisions"
              className="flex items-center justify-between gap-3 px-5 py-2 rounded-md bg-warning-soft border border-warning/25 hover:border-warning/40 transition-colors group"
            >
              <span className="flex items-center gap-2.5 text-sm font-medium text-ink">
                <ShieldAlert className="w-4 h-4 text-warning flex-shrink-0" />
                {t("overview.awaiting", { n: needsAttention })}
                {blocked > 0 && <span className="text-ink-2 font-normal">, {t("overview.ofWhichBlocked", { n: blocked })}</span>}
              </span>
              <span className="text-xs font-medium text-ink-2 group-hover:text-ink whitespace-nowrap">
                {t("overview.handle")}
              </span>
            </Link>
          )}

          <StatStrip total={total} waiting={waiting} blocked={blocked} deployed={deployed} />

          <Card className="overflow-hidden">
            <CardHeader title={t("overview.activity12m")} />
            <div className="px-5 pb-4 pt-2">
              <ActivityHeatmap data={activity} />
            </div>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
            <Card className="overflow-hidden lg:col-span-2">
              <CardHeader
                title={t("overview.recent")}
                actions={
                  <Link href="/dashboard/pipelines" className="text-xs font-medium text-accent hover:text-accent-hover">
                    {t("common.seeAll")}
                  </Link>
                }
              />

              {pipelines.length === 0 ? (
                <EmptyState
                  icon={GitBranch}
                  title={t("pipelines.empty")}
                  description={t("pipelines.emptyHint")}
                  tone="brand"
                />
              ) : (
                <ul className="divide-y divide-line">
                  {pipelines.slice(0, 7).map((p) => (
                    <li key={p.id}>
                      <Link
                        href={`/dashboard/pipelines/${p.id}`}
                        className="flex items-center gap-3.5 px-4 py-2 hover:bg-surface-2/60 transition-colors"
                      >
                        <div className="w-9 h-9 rounded bg-surface-2 text-ink-2 flex items-center justify-center text-xs font-semibold flex-shrink-0">
                          {p.repository.slice(0, 2).toUpperCase()}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-ink text-sm truncate">{p.repository}</span>
                            <span className="text-ink-3 text-xs flex-shrink-0">{p.branch}</span>
                          </div>
                          <p className="text-ink-2 text-xs truncate mt-0.5">{p.commit_message}</p>
                        </div>
                        <div className="flex flex-col items-end gap-1 flex-shrink-0">
                          <StatusBadge status={p.status} />
                          <span className="text-ink-3 text-[11px]">
                            {p.author} · {fmt.relative(p.created_at)}
                          </span>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card>
              <CardHeader title={t("overview.breakdown")} />
              <div className="p-4">
                <DecisionBreakdown counts={summary?.decision_counts ?? {}} />
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Bandeau de statistiques unique avec séparateurs internes plutôt que 4
 * cartes bordées séparées : un seul cadre, moins de bruit visuel répété,
 * les chiffres restent le point focal.
 */
function StatStrip({ total, waiting, blocked, deployed }: { total: number; waiting: number; blocked: number; deployed: number }) {
  const t = useT();
  const stats = [
    { label: t("overview.total"), value: total, icon: Layers, tone: "text-ink-2" },
    { label: t("status.WAITING_HUMAN"), value: waiting, icon: Clock, tone: "text-warning" },
    { label: t("overview.blocked"), value: blocked, icon: ShieldAlert, tone: "text-critical" },
    { label: t("overview.deployed"), value: deployed, icon: CheckCircle2, tone: "text-good" },
  ];

  return (
    <Card className="grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-line">
      {stats.map((s) => {
        const Icon = s.icon;
        return (
          <div key={s.label} className="p-5">
            <div className="flex items-center gap-1.5 mb-2">
              <Icon className={`w-3.5 h-3.5 ${s.tone}`} />
              <span className="text-xs text-ink-3">{s.label}</span>
            </div>
            <p className="text-2xl font-semibold text-ink tabular-nums leading-none">{s.value}</p>
          </div>
        );
      })}
    </Card>
  );
}

const BREAKDOWN_SEGMENTS: { key: string; decisions: string[]; label: MessageKey; className: string; icon: typeof CheckCircle2 }[] = [
  { key: "success", decisions: ["AUTO_AUTH", "DEROGATION"], label: "overview.approved", className: "bg-success", icon: CheckCircle2 },
  { key: "unstable", decisions: ["WAITING_HUMAN", "DEROGATION_REQUESTED"], label: "overview.pending", className: "bg-unstable", icon: Clock },
  { key: "failure", decisions: ["BLOCKED", "REJECTED_INVALID_SIGNATURE"], label: "overview.rejected", className: "bg-failure", icon: ShieldAlert },
];

/**
 * Répartition des décisions en barre empilée, la lecture la plus directe
 * d'une proportion, sans bibliothèque de graphiques : 376 ko de JavaScript
 * en moins pour l'utilisateur, pour un résultat plus lisible qu'un anneau.
 */
function DecisionBreakdown({ counts }: { counts: Record<string, number> }) {
  const t = useT();
  const segments = BREAKDOWN_SEGMENTS.map((s) => ({
    ...s,
    value: s.decisions.reduce((sum, d) => sum + (counts[d] ?? 0), 0),
  }));
  const total = segments.reduce((sum, s) => sum + s.value, 0);

  if (total === 0) {
    return <p className="text-sm text-ink-3">{t("overview.noDecisions")}</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold text-ink tabular-nums leading-none">{total}</span>
        <span className="text-xs text-ink-3">{t("overview.decisionWord")}{total > 1 ? "s" : ""}</span>
      </div>

      <div
        className="flex h-2.5 w-full rounded-sm overflow-hidden bg-surface-2"
        role="img"
        aria-label={segments.map((s) => `${t(s.label)} : ${s.value}`).join(", ")}
      >
        {segments.map((s) =>
          s.value > 0 ? (
            <div
              key={s.key}
              className={s.className}
              style={{ width: `${(s.value / total) * 100}%` }}
              title={`${t(s.label)} : ${s.value} (${Math.round((s.value / total) * 100)} %)`}
            />
          ) : null
        )}
      </div>

      <ul className="space-y-2">
        {segments.map((s) => {
          const Icon = s.icon;
          const pct = Math.round((s.value / total) * 100);
          return (
            <li key={s.key} className="flex items-center justify-between text-[13px]">
              <span className="flex items-center gap-2 text-ink-2">
                <span className={`w-2 h-2 rounded-sm ${s.className}`} aria-hidden="true" />
                <Icon className="w-3.5 h-3.5 text-ink-3" />
                {t(s.label)}
              </span>
              <span className="font-mono text-ink tabular-nums">
                {s.value}
                <span className="text-ink-3 ml-1.5">{pct} %</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
