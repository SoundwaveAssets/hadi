"use client";

import { useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { AlertCircle, GitBranch, KeyRound, Plus, Trash2, Users as UsersIcon } from "lucide-react";
import { useAddIdentity, useCreateUser, useIdentities, useRemoveIdentity, useResetPassword, useUpdateUser, useUsers, type Forge, type User, type UserRole } from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import { extractError } from "@/lib/errors";
import { StatusBadge } from "@/components/StatusBadge";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input, Select } from "@/components/ui/Field";
import { DataTable, type ColumnDef } from "@/components/ui/DataTable";

const ROLE_OPTIONS: UserRole[] = ["developer", "admin", "security_officer", "direction"];
const MIN_PASSWORD = 12;

export default function UsersPage() {
  const t = useT();
  const { data: users = [], isLoading, isError } = useUsers();
  const update = useUpdateUser();
  const [showCreate, setShowCreate] = useState(false);
  const [resetTarget, setResetTarget] = useState<User | null>(null);
  const [identitiesTarget, setIdentitiesTarget] = useState<User | null>(null);

  const patch = (id: number, changes: { role?: UserRole; is_active?: boolean }, errorKey: MessageKey) =>
    update.mutate({ id, ...changes }, { onError: (err) => toast.error(extractError(err, t(errorKey))) });

  const columns = useMemo<ColumnDef<User, unknown>[]>(
    () => [
      {
        accessorKey: "username",
        header: t("common.user"),
        cell: ({ row: { original: u } }) => (
          <>
            <div className="font-medium text-ink">{u.username}</div>
            {u.email && <div className="text-ink-3 text-xs">{u.email}</div>}
            {u.must_change_password && (
              <div className="flex items-center gap-1 text-warning text-xs mt-0.5">
                <AlertCircle className="w-3 h-3" /> {t("password.forcedTitle")}
              </div>
            )}
          </>
        ),
      },
      {
        accessorKey: "role",
        header: t("common.role"),
        meta: { width: "14rem" },
        cell: ({ row: { original: u } }) => (
          <Select value={u.role} onChange={(e) => patch(u.id, { role: e.target.value as UserRole }, "users.roleError")}>
            {ROLE_OPTIONS.map((r) => <option key={r} value={r}>{t(`role.${r}` as MessageKey)}</option>)}
          </Select>
        ),
      },
      {
        accessorKey: "is_active",
        header: t("common.status"),
        meta: { width: "9rem" },
        cell: ({ getValue }) => <StatusBadge status={getValue<boolean>() ? "active" : "inactive"} />,
      },
      {
        id: "actions",
        header: t("common.actions"),
        enableSorting: false,
        meta: { align: "right", width: "22rem" },
        cell: ({ row: { original: u } }) => (
          <span className="space-x-3">
            <button onClick={() => setIdentitiesTarget(u)} className="inline-flex items-center gap-1 text-ink-3 hover:text-ink-2 text-xs font-medium">
              <GitBranch className="w-3.5 h-3.5" /> {t("users.identities")}
            </button>
            <button onClick={() => setResetTarget(u)} className="inline-flex items-center gap-1 text-ink-3 hover:text-ink-2 text-xs font-medium">
              <KeyRound className="w-3.5 h-3.5" /> {t("users.reset")}
            </button>
            <button onClick={() => patch(u.id, { is_active: !u.is_active }, "users.statusError")} className="text-ink-3 hover:text-ink-2 text-xs font-medium">
              {u.is_active ? t("common.disable") : t("users.reactivate")}
            </button>
          </span>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- patch dépend de `update`, stable entre rendus
    [t]
  );

  return (
    <div className="space-y-4">
      <PageHeader title={t("page.users")} actions={<Button icon={Plus} onClick={() => setShowCreate(true)}>{t("users.new")}</Button>} />
      {isError ? (
        <EmptyState icon={UsersIcon} title={t("users.loadError")} />
      ) : !isLoading && users.length === 0 ? (
        <EmptyState icon={UsersIcon} title={t("users.empty")} />
      ) : (
        <DataTable columns={columns} data={users} rowKey={(u) => u.id} isLoading={isLoading} />
      )}
      {showCreate && <CreateUserModal onClose={() => setShowCreate(false)} />}
      {resetTarget && <ResetPasswordModal user={resetTarget} onClose={() => setResetTarget(null)} />}
      {identitiesTarget && <IdentitiesModal user={identitiesTarget} onClose={() => setIdentitiesTarget(null)} />}
    </div>
  );
}

const createSchema = z.object({
  username: z.string().trim().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$/),
  email: z.string().trim().email().or(z.literal("")),
  password: z.string().min(MIN_PASSWORD),
  role: z.enum(ROLE_OPTIONS),
});

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const t = useT();
  const create = useCreateUser();
  const form = useForm<z.infer<typeof createSchema>>({
    resolver: zodResolver(createSchema),
    defaultValues: { username: "", email: "", password: "", role: "developer" },
  });
  const { errors } = form.formState;

  const submit = form.handleSubmit((values) =>
    create.mutate(
      { ...values, email: values.email || null },
      { onSuccess: onClose, onError: (err) => toast.error(extractError(err, t("users.createError"))) }
    )
  );

  return (
    <Modal onClose={onClose} title={t("users.new")}>
      <form onSubmit={submit} className="space-y-4">
        <Input label={t("login.username")} {...form.register("username")} error={errors.username?.message} required autoFocus />
        <Input label={t("users.emailOptional")} type="email" {...form.register("email")} error={errors.email?.message} />
        <Input label={t("users.initialPassword")} type="password" {...form.register("password")} error={errors.password?.message} hint={t("password.newHint", { n: MIN_PASSWORD })} required />
        <Controller
          control={form.control}
          name="role"
          render={({ field }) => (
            <Select label={t("common.role")} value={field.value} onChange={(e) => field.onChange(e.target.value)}>
              {ROLE_OPTIONS.map((r) => <option key={r} value={r}>{t(`role.${r}` as MessageKey)}</option>)}
            </Select>
          )}
        />
        <p className="text-xs text-ink-3">{t("users.mustChangeHint")}</p>
        <Button type="submit" isLoading={create.isPending} className="w-full">{t("users.create")}</Button>
      </form>
    </Modal>
  );
}

function ResetPasswordModal({ user, onClose }: { user: User; onClose: () => void }) {
  const t = useT();
  const reset = useResetPassword();
  const form = useForm<{ new_password: string }>({
    resolver: zodResolver(z.object({ new_password: z.string().min(MIN_PASSWORD) })),
    defaultValues: { new_password: "" },
  });

  const submit = form.handleSubmit(({ new_password }) =>
    reset.mutate({ id: user.id, new_password }, { onSuccess: onClose, onError: (err) => toast.error(extractError(err, t("users.resetError"))) })
  );

  return (
    <Modal onClose={onClose} title={t("users.resetTitle", { name: user.username })}>
      <form onSubmit={submit} className="space-y-4">
        <Input label={t("password.new")} type="password" {...form.register("new_password")} error={form.formState.errors.new_password?.message} required autoFocus />
        <p className="text-xs text-ink-3">{t("users.mustChangeNextHint")}</p>
        <Button type="submit" variant="dark" isLoading={reset.isPending} className="w-full">{t("users.reset")}</Button>
      </form>
    </Modal>
  );
}

const FORGES: Forge[] = ["gitea", "github", "gitlab"];
const identitySchema = z.object({ provider: z.enum(FORGES), login: z.string().trim().min(1).max(255), external_id: z.string().trim().max(64) });

/** Comptes de forge reliés à l'utilisateur : c'est ce qui rend ses pushs attribuables et vérifiés. */
function IdentitiesModal({ user, onClose }: { user: User; onClose: () => void }) {
  const t = useT();
  const { data: identities = [], isLoading } = useIdentities(user.id);
  const add = useAddIdentity(user.id);
  const remove = useRemoveIdentity(user.id);
  const form = useForm<z.infer<typeof identitySchema>>({ resolver: zodResolver(identitySchema), defaultValues: { provider: "gitea", login: "", external_id: "" } });

  const submit = form.handleSubmit(({ provider, login, external_id }) =>
    add.mutate(
      { provider, login, external_id: external_id || undefined },
      { onSuccess: () => form.reset({ provider, login: "", external_id: "" }), onError: (err) => toast.error(extractError(err, t("users.identityAddError"))) }
    )
  );

  return (
    <Modal onClose={onClose} title={t("users.identitiesTitle", { name: user.username })} description={t("users.identitiesHint")} size="md">
      <div className="space-y-4">
        {isLoading ? null : identities.length === 0 ? (
          <p className="text-sm text-ink-3">{t("users.identitiesEmpty")}</p>
        ) : (
          <ul className="divide-y divide-line border border-line rounded">
            {identities.map((identity) => (
              <li key={identity.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="min-w-0 truncate">
                  <span className="text-ink-3 mr-2">{identity.provider}</span>
                  <span className="font-mono text-ink">{identity.login}</span>
                  {identity.external_id && <span className="text-ink-3 ml-2 text-xs">#{identity.external_id}</span>}
                </span>
                <button
                  onClick={() => remove.mutate(identity.id, { onError: (err) => toast.error(extractError(err, t("users.identityRemoveError"))) })}
                  className="text-ink-3 hover:text-critical flex-shrink-0"
                  aria-label={t("common.delete")}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={submit} className="grid grid-cols-[8rem_1fr] gap-3 items-end">
          <Controller
            control={form.control}
            name="provider"
            render={({ field }) => (
              <Select label={t("repos.forge")} value={field.value} onChange={(e) => field.onChange(e.target.value)}>
                {FORGES.map((f) => <option key={f} value={f}>{f}</option>)}
              </Select>
            )}
          />
          <Input label={t("users.identityLogin")} {...form.register("login")} error={form.formState.errors.login?.message} mono autoFocus />
          <div className="col-span-2 grid grid-cols-[1fr_auto] gap-3 items-end">
            <Input label={t("users.identityExternalId")} {...form.register("external_id")} mono />
            <Button type="submit" isLoading={add.isPending}>{t("users.identityAdd")}</Button>
          </div>
        </form>
      </div>
    </Modal>
  );
}
