"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import Link from "next/link";
import { CheckCircle2, GitBranch, ShieldAlert, ShieldCheck } from "lucide-react";
import { useApprove, usePending, type AuditEntry } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { extractError } from "@/lib/errors";
import { StatusBadge } from "@/components/StatusBadge";
import { IdentityBadge } from "@/components/IdentityBadge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { CenteredSpinner } from "@/components/ui/Spinner";
import { RepositorySelector } from "@/components/RepositorySelector";
import { useAuth } from "@/contexts/AuthContext";

export default function DecisionsPage() {
  const t = useT();
  const { user } = useAuth();
  const [repository, setRepository] = useState("");
  const canApprove = user?.role === "admin" || user?.role === "security_officer";
  const { data: entries = [], isLoading, isError } = usePending(repository || undefined);

  if (!canApprove) {
    return (
      <div className="space-y-4">
        <PageHeader title={t("page.decisions")} />
        <Card>
          <EmptyState
            icon={GitBranch}
            title={t("decisions.adminOnly")}
            description={
              <>
                {t("decisions.adminOnlyHint")}{" "}
                <Link href="/dashboard/pipelines" className="text-accent hover:text-accent-hover font-medium">{t("decisions.yourPipelines")}</Link>{" "}
                {t("common.or")} <code className="bg-surface-2 px-1.5 py-0.5 rounded text-xs">hadi history &lt;commit&gt;</code> {t("decisions.viaCli")}
              </>
            }
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title={t("page.decisions")} actions={<RepositorySelector value={repository} onChange={setRepository} />} />
      <Card className="overflow-hidden">
        {isLoading ? (
          <CenteredSpinner className="py-12" />
        ) : isError ? (
          <EmptyState icon={GitBranch} title={t("decisions.loadError")} />
        ) : entries.length === 0 ? (
          <EmptyState icon={CheckCircle2} title={t("decisions.allClear")} description={t("decisions.allClearHint")} />
        ) : (
          <ul className="divide-y divide-line">
            {entries.map((entry) => <PendingRow key={entry.id} entry={entry} currentUser={user?.username} />)}
          </ul>
        )}
      </Card>
    </div>
  );
}

const justificationSchema = z.object({ justification: z.string().trim().min(1) });

function PendingRow({ entry, currentUser }: { entry: AuditEntry; currentUser?: string }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const approve = useApprove();
  const form = useForm<{ justification: string }>({ resolver: zodResolver(justificationSchema), defaultValues: { justification: "" } });

  const awaitingSecondApproval = entry.decision === "DEROGATION_PENDING";
  const isOwnFirstApproval = awaitingSecondApproval && entry.approved_by === currentUser;

  const submit = form.handleSubmit(({ justification }) =>
    approve.mutate(
      { id: entry.id, justification },
      { onSuccess: (result) => { setOpen(false); toast.success(result.message); }, onError: (err) => toast.error(extractError(err, t("decisions.approveError"))) }
    )
  );

  return (
    <li className="p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-ink">{entry.repository_name}</span>
            <StatusBadge status={entry.decision} />
          </div>
          <p className="text-sm text-ink-3 mt-1 flex items-center gap-1.5 flex-wrap">
            <IdentityBadge username={entry.developer_username} source={entry.developer_identity_source} />
            <span>{t("decisions.scoreLabel")} {entry.ai_anomaly_score ?? "-"} {t("decisions.vulnsLabel")} {entry.sonarqube_vulnerabilities ?? "-"}</span>
          </p>
          <p className="text-sm text-ink-2 mt-1.5">{entry.justification}</p>
          {entry.ai_explanation && <p className="text-xs text-ink-3 mt-1">{t("decisions.explanation")} {entry.ai_explanation}</p>}
          {awaitingSecondApproval && (
            <p className="flex items-center gap-1.5 text-xs text-warning mt-1.5 font-medium">
              <ShieldCheck className="w-3.5 h-3.5" />
              {isOwnFirstApproval ? t("decisions.ownFirstApproval") : t("decisions.firstApprovalBy", { name: entry.approved_by ?? "" })}
            </p>
          )}
        </div>
        {!isOwnFirstApproval && (
          <Button size="sm" icon={ShieldAlert} onClick={() => setOpen((v) => !v)} className="flex-shrink-0">
            {awaitingSecondApproval ? t("decisions.confirmSecond") : t("decisions.grant")}
          </Button>
        )}
      </div>

      {open && (
        <form onSubmit={submit} className="mt-4 flex flex-col sm:flex-row gap-2 sm:items-start">
          <div className="flex-1">
            <Input {...form.register("justification")} placeholder={t("decisions.justificationPlaceholder")} error={form.formState.errors.justification?.message} autoFocus />
          </div>
          <Button type="submit" variant="dark" isLoading={approve.isPending} className="flex-shrink-0">{t("common.confirm")}</Button>
        </form>
      )}
    </li>
  );
}
