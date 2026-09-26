"use client";

import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { KeyRound, ScrollText, ShieldCheck } from "lucide-react";
import { useAdminEvents, useAudit, verifyAdminEvents, verifyAuditChain, type AdminEvent, type AuditEntry, type ChainVerification } from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import { useFormatDate } from "@/lib/format";
import { extractError } from "@/lib/errors";
import { StatusBadge } from "@/components/StatusBadge";
import { IdentityBadge } from "@/components/IdentityBadge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { Tabs } from "@/components/ui/Tabs";
import { Select } from "@/components/ui/Field";
import { DataTable, type ColumnDef } from "@/components/ui/DataTable";
import { FilterInput } from "@/components/devtools/FilterInput";

const PAGE_SIZE = 25;
type Tab = "decisions" | "admin";

export default function AuditPage() {
  const t = useT();
  const [tab, setTab] = useState<Tab>("decisions");
  const verify = useMutation({
    mutationFn: tab === "decisions" ? verifyAuditChain : verifyAdminEvents,
    onSuccess: (result: ChainVerification) => (result.status === "intact" ? toast.success(result.message) : toast.error(result.message, { duration: 10_000 })),
    onError: (err) => toast.error(extractError(err, t("audit.verify"))),
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("page.audit")}
        actions={<Button variant="dark" icon={ShieldCheck} onClick={() => verify.mutate()} isLoading={verify.isPending}>{t("audit.verify")}</Button>}
      />
      <Tabs
        tabs={[
          { key: "decisions", label: t("audit.decisions"), icon: ScrollText },
          { key: "admin", label: t("audit.adminEvents"), icon: KeyRound },
        ]}
        active={tab}
        onChange={(key) => setTab(key as Tab)}
      />
      {tab === "decisions" ? <DecisionsTab /> : <AdminEventsTab />}
    </div>
  );
}

// --- décisions --------------------------------------------------------------------

function DecisionsTab() {
  const t = useT();
  const { dateTime, shortDateTime } = useFormatDate();
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<AuditEntry | null>(null);
  const { data, isLoading } = useAudit({ limit: PAGE_SIZE, offset });

  const columns = useMemo<ColumnDef<AuditEntry, unknown>[]>(
    () => [
      { accessorKey: "timestamp", header: t("common.timestamp"), meta: { width: "13%" }, cell: ({ getValue }) => <span className="text-ink-3 text-xs" title={dateTime(getValue<string>())}>{shortDateTime(getValue<string>())}</span> },
      { accessorKey: "repository_name", header: t("common.repository"), meta: { width: "16%" } },
      { accessorKey: "developer_username", header: t("common.developer"), meta: { width: "14%" }, cell: ({ row: { original: e } }) => <IdentityBadge username={e.developer_username} source={e.developer_identity_source} /> },
      { accessorKey: "commit_hash", header: t("common.commit"), meta: { width: "12%", mono: true }, cell: ({ getValue }) => getValue<string>().slice(0, 10) },
      { accessorKey: "decision", header: t("common.decision"), meta: { width: "37%" }, cell: ({ getValue }) => <StatusBadge status={getValue<string>()} /> },
      detailsColumn<AuditEntry>(t("common.details"), setSelected),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- les formateurs de date sont stables
    [t]
  );

  if (!isLoading && data?.total === 0) return <EmptyState icon={ScrollText} title={t("audit.empty")} />;

  return (
    <>
      <DataTable
        columns={columns}
        data={data?.entries ?? []}
        rowKey={(e) => e.id}
        isLoading={isLoading}
        pagination={data ? { offset, limit: PAGE_SIZE, total: data.total, onChange: setOffset } : undefined}
      />
      {selected && (
        <Modal title={t("audit.entry", { id: selected.id })} onClose={() => setSelected(null)} size="md">
          <div className="space-y-3.5 text-sm">
            <Field label={t("common.decision")}><StatusBadge status={selected.decision} /></Field>
            <div className="grid grid-cols-2 gap-3.5">
              <Field label={t("common.timestamp")}>{dateTime(selected.timestamp)}</Field>
              <Field label={t("common.repository")}>{selected.repository_name}</Field>
              <Field label={t("common.developer")}>{selected.developer_username}</Field>
              <Field label={t("common.commit")}><span className="font-mono text-xs break-all">{selected.commit_hash}</span></Field>
            </div>
            <Field label={t("common.justification")}><span className="leading-relaxed">{selected.justification}</span></Field>
          </div>
        </Modal>
      )}
    </>
  );
}

// --- actions d'administration -------------------------------------------------------

/** Préfixes d'action proposés au filtre, dans l'ordre d'affichage. */
const ACTION_GROUPS = ["user", "auth", "integration", "pipeline", "policy", "module", "settings", "notifications"] as const;

function AdminEventsTab() {
  const t = useT();
  const { dateTime, shortDateTime } = useFormatDate();
  const [offset, setOffset] = useState(0);
  const [actor, setActor] = useState("");
  const [group, setGroup] = useState("");
  const [selected, setSelected] = useState<AdminEvent | null>(null);
  const { data, isLoading } = useAdminEvents({ limit: PAGE_SIZE, offset, actor: actor || undefined, action: group ? `${group}.` : undefined });

  const actionLabel = (action: string) => {
    const key = `audit.action.${action}` as MessageKey;
    const label = t(key);
    return label === key ? action : label;
  };

  const columns = useMemo<ColumnDef<AdminEvent, unknown>[]>(
    () => [
      { accessorKey: "timestamp", header: t("common.timestamp"), meta: { width: "13%" }, cell: ({ getValue }) => <span className="text-ink-3 text-xs" title={dateTime(getValue<string>())}>{shortDateTime(getValue<string>())}</span> },
      {
        accessorKey: "actor",
        header: t("audit.actor"),
        meta: { width: "16%" },
        cell: ({ row: { original: e } }) => (
          <>
            <div className="text-ink truncate">{e.actor}</div>
            <div className="text-ink-3 text-xs">{t(`role.${e.actor_role}` as MessageKey)}</div>
          </>
        ),
      },
      { accessorKey: "action", header: t("audit.action"), meta: { width: "22%" }, cell: ({ getValue }) => <span className="font-medium text-ink-2">{actionLabel(getValue<string>())}</span> },
      {
        id: "target",
        accessorFn: (e) => e.target_label ?? e.target_id ?? "",
        header: t("audit.target"),
        meta: { width: "27%" },
        cell: ({ row: { original: e } }) => (
          <span className="truncate">
            <span className="text-ink-3 text-xs mr-1.5">{e.target_type}</span>
            {e.target_label ?? e.target_id}
          </span>
        ),
      },
      { accessorKey: "ip", header: t("audit.ip"), meta: { width: "14%", mono: true }, cell: ({ getValue }) => getValue<string | null>() ?? "-" },
      detailsColumn<AdminEvent>(t("common.details"), setSelected),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- les formateurs de date et actionLabel ne dépendent que de t
    [t]
  );

  const filtered = Boolean(actor || group);
  if (!isLoading && data?.total === 0 && !filtered) return <EmptyState icon={KeyRound} title={t("audit.adminEmpty")} />;

  return (
    <>
      <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
        <FilterInput value={actor} onChange={(value) => { setActor(value); setOffset(0); }} placeholder={t("audit.filterActor")} className="w-full sm:w-56" />
        <Select value={group} onChange={(e) => { setGroup(e.target.value); setOffset(0); }} className="sm:w-56">
          <option value="">{t("audit.allActions")}</option>
          {ACTION_GROUPS.map((g) => <option key={g} value={g}>{t(`audit.group.${g}`)}</option>)}
        </Select>
      </div>
      <DataTable
        columns={columns}
        data={data?.entries ?? []}
        rowKey={(e) => e.id}
        isLoading={isLoading}
        pagination={data ? { offset, limit: PAGE_SIZE, total: data.total, onChange: setOffset } : undefined}
        empty={t("common.noResults")}
      />
      {selected && (
        <Modal title={t("audit.event", { id: selected.id })} onClose={() => setSelected(null)} size="lg">
          <div className="space-y-3.5 text-sm">
            <div className="grid grid-cols-2 gap-3.5">
              <Field label={t("common.timestamp")}>{dateTime(selected.timestamp)}</Field>
              <Field label={t("audit.actor")}>{selected.actor} · {t(`role.${selected.actor_role}` as MessageKey)}</Field>
              <Field label={t("audit.action")}>{actionLabel(selected.action)}</Field>
              <Field label={t("audit.target")}>{selected.target_type} · {selected.target_label ?? selected.target_id ?? "-"}</Field>
              <Field label={t("audit.ip")}><span className="font-mono text-xs">{selected.ip ?? "-"}</span></Field>
            </div>
            {(selected.before || selected.after) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                <Json label={t("audit.before")} value={selected.before} />
                <Json label={t("audit.after")} value={selected.after} />
              </div>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

// --- partagé ------------------------------------------------------------------------

function detailsColumn<T>(label: string, onSelect: (row: T) => void): ColumnDef<T, unknown> {
  return {
    id: "details",
    header: label,
    enableSorting: false,
    meta: { align: "right", width: "8%" },
    cell: ({ row }) => <button onClick={() => onSelect(row.original)} className="text-accent hover:text-accent-hover text-xs font-medium">{label}</button>,
  };
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-ink-3 uppercase tracking-wide mb-1">{label}</p>
      <p className="text-ink-2 truncate">{children}</p>
    </div>
  );
}

function Json({ label, value }: { label: string; value: string | null }) {
  const pretty = useMemo(() => {
    if (!value) return null;
    try {
      const parsed = JSON.parse(value) as Record<string, unknown>;
      return Object.keys(parsed).length ? JSON.stringify(parsed, null, 2) : null;
    } catch {
      return value;
    }
  }, [value]);
  return (
    <div>
      <p className="text-xs text-ink-3 uppercase tracking-wide mb-1">{label}</p>
      <pre className="bg-surface-2 border border-line rounded p-2.5 text-xs font-mono text-ink-2 overflow-x-auto min-h-10 whitespace-pre-wrap break-all">{pretty ?? "—"}</pre>
    </div>
  );
}
