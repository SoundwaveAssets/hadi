"use client";

import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Activity,
  CheckCircle2,
  Clock,
  Database,
  HelpCircle,
  GitBranch,
  GitFork,
  GitMerge,
  Rocket,
  Server,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useIntegrationsHealth, verifyAuditChain, type HealthEntry } from "@/lib/api";
import { extractError } from "@/lib/errors";
import { useT, type MessageKey } from "@/lib/i18n";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { CenteredSpinner } from "@/components/ui/Spinner";

const TOOL_META: { key: string; label: MessageKey | string; icon: LucideIcon }[] = [
  { key: "database", label: "monitoring.db", icon: Database },
  { key: "gitea", label: "Gitea", icon: GitBranch },
  { key: "github", label: "GitHub", icon: GitFork },
  { key: "gitlab", label: "GitLab", icon: GitMerge },
  { key: "jenkins", label: "Jenkins", icon: Server },
  { key: "sonarqube", label: "SonarQube", icon: TerminalSquare },
  { key: "argocd", label: "Argo CD", icon: Rocket },
  { key: "ai", label: "monitoring.ai", icon: Sparkles },
];

export default function MonitoringPage() {
  const t = useT();
  // Rafraîchie toutes les 30 s : la page sert de tableau de bord d'exploitation.
  const { data: health = {}, isLoading, isFetching, refetch } = useIntegrationsHealth(30_000);
  const verify = useMutation({
    mutationFn: verifyAuditChain,
    onSuccess: (result) => (result.status === "intact" ? toast.success(result.message) : toast.error(result.message, { duration: 10_000 })),
    onError: (err) => toast.error(extractError(err, t("audit.verify"))),
  });

  // Uniquement les clés affichées (TOOL_META), pour que le total corresponde à l'écran.
  const displayedHealth = TOOL_META.map((t) => health[t.key]).filter((h): h is HealthEntry => Boolean(h));
  const reachableCount = displayedHealth.filter((h) => h.reachable === true).length;
  const configuredCount = displayedHealth.filter((h) => h.configured).length;

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("page.monitoring")}
        actions={
          <Button variant="secondary" icon={Activity} onClick={() => refetch()} isLoading={isFetching}>
            {t("common.refresh")}
          </Button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Card className="p-5 flex items-center gap-4">
          <div className="w-11 h-11 rounded-md bg-good-soft text-good flex items-center justify-center flex-shrink-0">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <p className="text-2xl font-semibold text-ink leading-none">{reachableCount}</p>
            <p className="text-sm text-ink-3 mt-1.5">{t("monitoring.reachableCount")}</p>
          </div>
        </Card>
        <Card className="p-5 flex items-center gap-4">
          <div className="w-11 h-11 rounded-md bg-surface-2 text-ink-2 flex items-center justify-center flex-shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <p className="text-2xl font-semibold text-ink leading-none">{configuredCount} / {TOOL_META.length}</p>
            <p className="text-sm text-ink-3 mt-1.5">{t("monitoring.configuredCount")}</p>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title={t("monitoring.state")}
          description={t("monitoring.stateHint")}
        />
        {isLoading ? (
          <CenteredSpinner className="py-10" />
        ) : (
          <ul className="divide-y divide-line">
            {TOOL_META.map((tool) => {
              const entry = health[tool.key];
              const Icon = tool.icon;
              return (
                <li key={tool.key} className="flex items-center justify-between gap-4 px-4 py-2">
                  <div className="flex items-center gap-3 min-w-0">
                    <Icon className="w-4 h-4 text-ink-3 flex-shrink-0" />
                    <div className="min-w-0">
                      <span className="text-sm font-medium text-ink-2 truncate block">{tool.label.includes(".") ? t(tool.label as MessageKey) : tool.label}</span>
                      {tool.key === "ai" && entry?.message && (
                        <span className="text-xs text-ink-3 truncate block">{entry.message}</span>
                      )}
                    </div>
                  </div>
                  {tool.key === "ai" ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-good flex-shrink-0">
                      <CheckCircle2 className="w-3.5 h-3.5" /> {t("common.active")}
                    </span>
                  ) : (
                    <ToolStatus entry={entry} />
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card className="p-4 space-y-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h3 className="text-sm font-semibold text-ink">{t("monitoring.integrity")}</h3>
            <p className="text-xs text-ink-3 mt-0.5">
              {t("monitoring.integrityHint")}
            </p>
          </div>
          <Button variant="secondary" icon={ShieldCheck} onClick={() => verify.mutate()} isLoading={verify.isPending}>
            {t("audit.verify")}
          </Button>
        </div>
      </Card>
    </div>
  );
}

function ToolStatus({ entry }: { entry?: HealthEntry }) {
  const t = useT();
  if (!entry || !entry.configured) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-3">
        <HelpCircle className="w-3.5 h-3.5" /> {t("common.notConfigured")}
      </span>
    );
  }
  if (entry.reachable === null) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-accent">
        <Clock className="w-3.5 h-3.5" /> {t("common.configured")}
      </span>
    );
  }
  return entry.reachable ? (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-good">
      <CheckCircle2 className="w-3.5 h-3.5" /> {t("common.reachable")}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-critical" title={entry.error}>
      <XCircle className="w-3.5 h-3.5" /> {t("common.unreachable")}
    </span>
  );
}
