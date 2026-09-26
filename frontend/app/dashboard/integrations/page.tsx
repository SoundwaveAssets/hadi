"use client";

import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Pencil, Zap } from "lucide-react";
import { testTool, useIntegrationsHealth, useSaveTool, useToolConfig, type HealthEntry, type TestResult, type ToolCredentials, type ToolKey } from "@/lib/api";
import { extractError } from "@/lib/errors";
import { useT, type MessageKey } from "@/lib/i18n";
import { PageHeader } from "@/components/ui/PageHeader";
import { Input } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { CenteredSpinner } from "@/components/ui/Spinner";
import { StatusIcon } from "@/components/devtools/StatusIcon";
import { cn } from "@/lib/cn";

interface ToolDef {
  key: ToolKey;
  name: string;
  hasUser: boolean;
  /** URL facultative, valeur par défaut affichée. */
  defaultUrl?: string;
}

const TOOLS: ToolDef[] = [
  { key: "gitea", name: "Gitea", hasUser: false },
  { key: "github", name: "GitHub", hasUser: false, defaultUrl: "https://api.github.com" },
  { key: "gitlab", name: "GitLab", hasUser: false, defaultUrl: "https://gitlab.com" },
  { key: "jenkins", name: "Jenkins", hasUser: true },
  { key: "sonarqube", name: "SonarQube", hasUser: false },
  { key: "argocd", name: "Argo CD", hasUser: false },
];

interface ToolRow {
  def: ToolDef;
  url: string;
  user: string;
  hasSecret: boolean;
  health?: HealthEntry;
}

interface Outcome {
  code: "SUCCESS" | "FAILED" | "IN_PROGRESS" | "NOT_EXECUTED";
  label: string;
  detail: string | null;
}

function useResultLabel() {
  const t = useT();
  return (r: TestResult): string => {
    const key = `integrations.result.${r.code ?? ""}` as MessageKey;
    const label = t(key);
    const base = label === key ? r.message ?? "" : label;
    return r.http && r.code !== "auth_ok" && r.code !== "no_auth" ? `${base} HTTP ${r.http}` : base;
  };
}

/** Lance un test de connexion et le traduit en état affichable ; une seule mutation par outil. */
function useConnectionTest(tool: ToolKey) {
  const t = useT();
  const resultLabel = useResultLabel();
  const test = useMutation({ mutationFn: (payload: ToolCredentials) => testTool(tool, payload) });

  let outcome: Outcome | null = null;
  if (test.isPending) outcome = { code: "IN_PROGRESS", label: t("common.testing"), detail: null };
  else if (test.isError) outcome = { code: "FAILED", label: t("common.unreachable"), detail: extractError(test.error, t("integrations.testError")) };
  else if (test.data) {
    const ok = test.data.reachable && test.data.code !== "auth_refused";
    outcome = { code: ok ? "SUCCESS" : "FAILED", label: test.data.reachable ? t("common.reachable") : t("common.unreachable"), detail: resultLabel(test.data) };
  }
  return { run: test.mutate, reset: test.reset, isPending: test.isPending, outcome };
}

export default function IntegrationsPage() {
  const t = useT();
  const { data: config, isLoading: loadingConfig, isError } = useToolConfig();
  const { data: health, isLoading: loadingHealth } = useIntegrationsHealth();
  const [editing, setEditing] = useState<ToolRow | null>(null);

  const rows: ToolRow[] = TOOLS.map((def) => ({
    def,
    url: (config?.[`${def.key}_url`] as string | undefined) || "",
    user: def.key === "jenkins" ? config?.jenkins_user || "" : "",
    hasSecret: Boolean(config?.[`${def.key}_token`]),
    health: health?.[def.key],
  }));

  return (
    <div className="space-y-4">
      <PageHeader title={t("page.integrations")} />
      {isError && <p className="text-[13px] text-failure">{t("integrations.loadError")}</p>}
      {loadingConfig || loadingHealth ? (
        <CenteredSpinner className="py-10" />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {rows.map((row) => <ToolCard key={row.def.key} row={row} onEdit={() => setEditing(row)} />)}
        </div>
      )}
      {editing && <EditToolModal row={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function ToolCard({ row, onEdit }: { row: ToolRow; onEdit: () => void }) {
  const t = useT();
  const test = useConnectionTest(row.def.key);

  const status: Outcome = test.outcome ?? (
    !row.health?.configured ? { code: "NOT_EXECUTED", label: t("common.notConfigured"), detail: null }
    : row.health.reachable === null ? { code: "NOT_EXECUTED", label: t("common.notTested"), detail: null }
    : row.health.reachable ? { code: "SUCCESS", label: t("common.reachable"), detail: null }
    : { code: "FAILED", label: t("common.unreachable"), detail: row.health.error || null }
  );
  const isFailure = status.code === "FAILED";
  const url = row.url || row.def.defaultUrl || "";

  return (
    <div className="rounded-md border border-line bg-surface flex flex-col">
      <div className="flex items-center gap-2.5 h-10 px-3 border-b border-line">
        <StatusIcon status={status.code} size="sm" />
        <span className="text-[13px] font-semibold text-ink">{row.def.name}</span>
        <span className={cn("ml-auto text-[12px] whitespace-nowrap", isFailure ? "text-failure" : "text-ink-3")}>{status.label}</span>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 px-3 py-2.5 text-[12.5px] flex-1">
        <dt className="text-ink-3 whitespace-nowrap">{t("integrations.url")}</dt>
        <dd className="font-mono text-ink-2 truncate">
          {row.url || (row.def.defaultUrl ? <span className="text-ink-3">{row.def.defaultUrl}</span> : <span className="text-ink-3 font-sans">{t("common.notConfigured")}</span>)}
        </dd>
        <dt className="text-ink-3 whitespace-nowrap">{t("integrations.account")}</dt>
        <dd className="font-mono text-ink-2 truncate">
          {row.def.hasUser ? row.user || <span className="text-ink-3 font-sans">{t("common.none")}</span> : <span className="text-ink-3 font-sans">{t("common.notRequired")}</span>}
        </dd>
        <dt className="text-ink-3 whitespace-nowrap">{t("integrations.secret")}</dt>
        <dd className="text-ink-2">{row.hasSecret ? t("common.saved") : <span className="text-ink-3">{t("common.absent")}</span>}</dd>
        <dt className="text-ink-3 whitespace-nowrap">{t("integrations.test")}</dt>
        <dd className={cn("truncate", isFailure ? "text-failure" : "text-ink-2")} title={status.detail ?? undefined}>
          {status.detail ?? <span className="text-ink-3">{t("common.notTested")}</span>}
        </dd>
      </dl>
      <div className="flex items-center justify-end gap-1 px-2 py-1.5 border-t border-line bg-surface-2/50">
        <Button size="sm" variant="ghost" icon={Zap} onClick={() => test.run({ url, user: row.user || undefined })} disabled={!url} isLoading={test.isPending}>
          {t("common.test")}
        </Button>
        <Button size="sm" variant="ghost" icon={Pencil} onClick={onEdit}>{t("common.edit")}</Button>
      </div>
    </div>
  );
}

interface EditForm {
  url: string;
  user: string;
  secret: string;
}

function EditToolModal({ row, onClose }: { row: ToolRow; onClose: () => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const { def } = row;
  const form = useForm<EditForm>({ defaultValues: { url: row.url, user: row.user, secret: "" } });
  const values = useWatch({ control: form.control });
  const effectiveUrl = values.url || def.defaultUrl || "";
  const test = useConnectionTest(def.key);
  const save = useSaveTool();

  const credentials = (): ToolCredentials => ({ url: effectiveUrl, user: def.hasUser ? values.user || undefined : undefined, token: values.secret || undefined });

  const submit = form.handleSubmit(() =>
    save.mutate(
      { tool: def.key, ...credentials() },
      {
        onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["integrations-health"] }); toast.success(t("common.savedOk")); onClose(); },
        onError: (err) => toast.error(extractError(err, t("integrations.saveError"))),
      }
    )
  );

  return (
    <Modal title={def.name} onClose={onClose} size="md">
      <form onSubmit={submit} className="space-y-3">
        <Input label={t("integrations.url")} {...form.register("url")} mono required={!def.defaultUrl} placeholder={def.defaultUrl ?? "https://"} />
        {def.hasUser && <Input label={t("integrations.account")} {...form.register("user")} mono />}
        <Input type="password" label={t("integrations.secret.token")} {...form.register("secret")} placeholder={row.hasSecret ? t("integrations.keepSecret") : ""} mono />
        {test.outcome && (
          <p className="flex items-center gap-2 text-[12.5px] text-ink-2">
            <StatusIcon status={test.outcome.code} size="sm" />
            {test.outcome.detail ?? test.outcome.label}
          </p>
        )}
        <div className="flex items-center gap-2 pt-1">
          <Button type="button" size="sm" variant="secondary" icon={Zap} onClick={() => test.run(credentials())} disabled={!effectiveUrl} isLoading={test.isPending}>
            {t("common.test")}
          </Button>
          <span className="flex-1" />
          <Button type="button" size="sm" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" size="sm" isLoading={save.isPending} disabled={!effectiveUrl}>{t("common.save")}</Button>
        </div>
      </form>
    </Modal>
  );
}
