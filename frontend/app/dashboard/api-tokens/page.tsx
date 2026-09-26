"use client";

import { useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Copy, KeySquare, Plus } from "lucide-react";
import { useApiTokens, useCreateToken, useRevokeToken, type ApiToken, type CreatedToken, type UserRole } from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import { extractError } from "@/lib/errors";
import { useFormatDate } from "@/lib/format";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input, Select } from "@/components/ui/Field";
import { DataTable, type ColumnDef } from "@/components/ui/DataTable";

const ROLE_OPTIONS: UserRole[] = ["developer", "admin", "security_officer", "direction"];

export default function ApiTokensPage() {
  const t = useT();
  const { dateTime } = useFormatDate();
  const { data: tokens = [], isLoading, isError } = useApiTokens();
  const revoke = useRevokeToken();
  const [showCreate, setShowCreate] = useState(false);
  const [created, setCreated] = useState<CreatedToken | null>(null);

  const columns = useMemo<ColumnDef<ApiToken, unknown>[]>(
    () => [
      {
        accessorKey: "name",
        header: t("common.name"),
        cell: ({ row: { original: row } }) => (
          <>
            <div className="font-medium text-ink">{row.name}</div>
            <div className="text-ink-3 text-xs">{t("common.createdBy")} {row.created_by}</div>
          </>
        ),
      },
      { accessorKey: "token_prefix", header: t("tokens.prefix"), meta: { mono: true, width: "10rem" }, cell: ({ getValue }) => `${getValue<string>()}…` },
      { accessorKey: "role", header: t("common.role"), meta: { width: "12rem" }, cell: ({ getValue }) => t(`role.${getValue<UserRole>()}` as MessageKey) },
      {
        accessorKey: "last_used_at",
        header: t("tokens.lastUsed"),
        meta: { width: "12rem" },
        cell: ({ getValue }) => <span className="text-ink-3 text-xs">{getValue<string | null>() ? dateTime(getValue<string>()) : t("common.never")}</span>,
      },
      {
        accessorKey: "is_revoked",
        header: t("common.status"),
        meta: { width: "8rem" },
        cell: ({ getValue }) =>
          getValue<boolean>() ? <span className="text-xs font-medium text-ink-3">{t("tokens.revoked")}</span> : <span className="text-xs font-medium text-good">{t("common.active")}</span>,
      },
      {
        id: "actions",
        header: t("common.actions"),
        enableSorting: false,
        meta: { align: "right", width: "8rem" },
        cell: ({ row: { original: row } }) =>
          !row.is_revoked && (
            <button
              onClick={() => revoke.mutate(row.id, { onError: (err) => toast.error(extractError(err, t("tokens.revokeError"))) })}
              className="text-critical text-xs font-medium"
            >
              {t("tokens.revoke")}
            </button>
          ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- revoke et dateTime sont stables entre rendus
    [t]
  );

  return (
    <div className="space-y-4">
      <PageHeader title={t("page.tokens")} actions={<Button icon={Plus} onClick={() => setShowCreate(true)}>{t("tokens.new")}</Button>} />
      {isError ? (
        <EmptyState icon={KeySquare} title={t("tokens.loadError")} />
      ) : !isLoading && tokens.length === 0 ? (
        <EmptyState icon={KeySquare} title={t("tokens.empty")} />
      ) : (
        <DataTable columns={columns} data={tokens} rowKey={(row) => row.id} isLoading={isLoading} />
      )}
      {showCreate && <CreateTokenModal onClose={() => setShowCreate(false)} onCreated={setCreated} />}
      {created && <RevealTokenModal name={created.name} token={created.token} onClose={() => setCreated(null)} />}
    </div>
  );
}

const createSchema = z.object({ name: z.string().trim().min(1).max(64), role: z.enum(ROLE_OPTIONS) });

function CreateTokenModal({ onClose, onCreated }: { onClose: () => void; onCreated: (token: CreatedToken) => void }) {
  const t = useT();
  const create = useCreateToken();
  const form = useForm<z.infer<typeof createSchema>>({ resolver: zodResolver(createSchema), defaultValues: { name: "", role: "developer" } });

  const submit = form.handleSubmit((values) =>
    create.mutate(values, {
      onSuccess: (token) => { onCreated(token); onClose(); },
      onError: (err) => toast.error(extractError(err, t("tokens.createError"))),
    })
  );

  return (
    <Modal onClose={onClose} title={t("tokens.newTitle")}>
      <form onSubmit={submit} className="space-y-4">
        <Input label={t("common.name")} {...form.register("name")} placeholder={t("tokens.namePlaceholder")} error={form.formState.errors.name?.message} required autoFocus />
        <Controller
          control={form.control}
          name="role"
          render={({ field }) => (
            <Select label={t("tokens.role")} value={field.value} onChange={(e) => field.onChange(e.target.value)}>
              {ROLE_OPTIONS.map((r) => <option key={r} value={r}>{t(`role.${r}` as MessageKey)}</option>)}
            </Select>
          )}
        />
        <Button type="submit" isLoading={create.isPending} className="w-full">{t("common.create")}</Button>
      </form>
    </Modal>
  );
}

function RevealTokenModal({ name, token, onClose }: { name: string; token: string; onClose: () => void }) {
  const t = useT();
  const copy = () => navigator.clipboard.writeText(token).then(() => toast.success(t("common.copiedExcl")));

  return (
    <Modal onClose={onClose} title={t("tokens.created", { name })} size="md">
      <p className="text-sm text-warning bg-warning-soft border border-warning/30 rounded p-3 mb-3">{t("tokens.copyNow")}</p>
      <div className="flex items-center gap-2">
        <code className="flex-1 bg-page border border-line rounded px-3 py-2 text-xs text-ink-2 overflow-x-auto">{token}</code>
        <button onClick={copy} className="p-2 rounded border border-line hover:bg-surface-2 text-ink-2" aria-label={t("common.copiedExcl")}>
          <Copy className="w-4 h-4" />
        </button>
      </div>
      <Button onClick={onClose} className="w-full mt-4">{t("common.done")}</Button>
    </Modal>
  );
}
