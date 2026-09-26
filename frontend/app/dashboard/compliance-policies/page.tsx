"use client";

import { useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Clock, Plus, ShieldQuestion, Trash2 } from "lucide-react";
import { useCreatePolicy, useDeletePolicy, usePolicies, useTogglePolicy, type CompliancePolicy, type PolicyType } from "@/lib/api";
import { useI18n, useT } from "@/lib/i18n";
import { extractError } from "@/lib/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input, Select } from "@/components/ui/Field";
import { CenteredSpinner } from "@/components/ui/Spinner";
import { Switch } from "@/components/ui/Switch";
import { cn } from "@/lib/cn";

/** Lundi = 0, comme allowed_days côté API ; libellés courts dans la langue courante. */
function useDayLabels(): string[] {
  const { lang } = useI18n();
  const locale = lang === "en" ? "en-GB" : "fr-FR";
  return Array.from({ length: 7 }, (_, i) => new Date(Date.UTC(2024, 0, 1 + i)).toLocaleDateString(locale, { weekday: "short", timeZone: "UTC" }));
}

export default function CompliancePoliciesPage() {
  const t = useT();
  const dayLabels = useDayLabels();
  const { data: policies = [], isLoading, isError } = usePolicies();
  const toggle = useTogglePolicy();
  const remove = useDeletePolicy();
  const [showCreate, setShowCreate] = useState(false);

  const describe = (p: CompliancePolicy) =>
    p.policy_type === "deployment_window"
      ? `${t("policies.window")} ${p.allowed_days ? p.allowed_days.split(",").map((d) => dayLabels[Number(d)]).join(", ") : t("policies.everyDay")}` +
        (p.allowed_start_hour !== null && p.allowed_end_hour !== null ? `, ${p.allowed_start_hour}h–${p.allowed_end_hour}h UTC` : "")
      : `${t("policies.reposContaining")} ${p.repository_pattern} ${t("policies.alwaysReviewed")}`;

  return (
    <div className="space-y-4">
      <PageHeader title={t("page.policies")} actions={<Button icon={Plus} onClick={() => setShowCreate(true)}>{t("policies.new")}</Button>} />

      <Card className="overflow-hidden">
        {isLoading ? (
          <CenteredSpinner />
        ) : isError ? (
          <EmptyState icon={ShieldQuestion} title={t("policies.loadError")} />
        ) : policies.length === 0 ? (
          <EmptyState icon={ShieldQuestion} title={t("policies.empty")} description={t("policies.emptyHint")} />
        ) : (
          <ul className="divide-y divide-line">
            {policies.map((p) => (
              <li key={p.id} className="p-5 flex items-start justify-between gap-4">
                <div className="flex items-start gap-3 min-w-0">
                  <div className={cn("p-2 rounded flex-shrink-0", p.is_active ? "bg-accent-soft text-accent" : "bg-surface-2 text-ink-3")}>
                    {p.policy_type === "deployment_window" ? <Clock className="w-4 h-4" /> : <ShieldQuestion className="w-4 h-4" />}
                  </div>
                  <div className="min-w-0">
                    <h4 className="text-sm font-semibold text-ink">{p.name}</h4>
                    <p className="text-xs text-ink-3 mt-0.5">{describe(p)}</p>
                    <p className="text-xs text-ink-3 mt-0.5">{t("common.createdByF")} {p.created_by}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <Switch
                    checked={p.is_active}
                    onChange={() => toggle.mutate(p.id, { onError: (err) => toast.error(extractError(err, t("common.toggleError"))) })}
                    label={`${p.is_active ? t("common.disable") : t("common.enable")} ${p.name}`}
                  />
                  <button
                    onClick={() => remove.mutate(p.id, { onError: (err) => toast.error(extractError(err, t("common.deleteError"))) })}
                    className="text-ink-3 hover:text-critical"
                    aria-label={t("common.deleteError")}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {showCreate && <CreatePolicyModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

const hour = z.number().int().min(0).max(23);
const schema = z.discriminatedUnion("policy_type", [
  z.object({
    policy_type: z.literal("deployment_window"),
    name: z.string().trim().min(1),
    allowed_days: z.array(z.number().int().min(0).max(6)).min(1),
    allowed_start_hour: hour,
    allowed_end_hour: hour,
  }),
  z.object({
    policy_type: z.literal("reinforced_repository"),
    name: z.string().trim().min(1),
    repository_pattern: z.string().trim().min(1),
  }),
]);

type PolicyForm = z.infer<typeof schema>;

function CreatePolicyModal({ onClose }: { onClose: () => void }) {
  const t = useT();
  const dayLabels = useDayLabels();
  const create = useCreatePolicy();
  const form = useForm<PolicyForm>({
    resolver: zodResolver(schema),
    defaultValues: { policy_type: "deployment_window", name: "", allowed_days: [0, 1, 2, 3, 4], allowed_start_hour: 8, allowed_end_hour: 18 },
  });
  const policyType = useWatch({ control: form.control, name: "policy_type" });
  const errors = form.formState.errors as Record<string, { message?: string } | undefined>;

  const submit = form.handleSubmit((values) => {
    const payload =
      values.policy_type === "deployment_window"
        ? {
            name: values.name,
            policy_type: values.policy_type,
            allowed_days: [...values.allowed_days].sort().join(","),
            allowed_start_hour: values.allowed_start_hour,
            allowed_end_hour: values.allowed_end_hour,
            repository_scope: null,
            repository_pattern: null,
          }
        : { name: values.name, policy_type: values.policy_type, repository_pattern: values.repository_pattern, allowed_days: null, allowed_start_hour: null, allowed_end_hour: null, repository_scope: null };
    create.mutate(payload, { onSuccess: onClose, onError: (err) => toast.error(extractError(err, t("policies.createError"))) });
  });

  return (
    <Modal onClose={onClose} title={t("policies.newTitle")} size="md">
      <form onSubmit={submit} className="space-y-4">
        <Input label={t("common.name")} {...form.register("name")} error={errors.name?.message} required autoFocus />
        <Controller
          control={form.control}
          name="policy_type"
          render={({ field }) => (
            <Select label={t("common.type")} value={field.value} onChange={(e) => field.onChange(e.target.value as PolicyType)}>
              <option value="deployment_window">{t("policies.type.window")}</option>
              <option value="reinforced_repository">{t("policies.type.reinforced")}</option>
            </Select>
          )}
        />

        {policyType === "deployment_window" ? (
          <>
            <Controller
              control={form.control}
              name="allowed_days"
              render={({ field }) => (
                <div>
                  <span className="block text-sm font-medium text-ink-2 mb-1.5">{t("policies.allowedDays")}</span>
                  <div className="flex gap-1.5 flex-wrap">
                    {dayLabels.map((label, day) => {
                      const selected = field.value.includes(day);
                      return (
                        <button
                          key={day}
                          type="button"
                          aria-pressed={selected}
                          onClick={() => field.onChange(selected ? field.value.filter((d) => d !== day) : [...field.value, day])}
                          className={cn("px-2.5 py-1.5 rounded text-xs font-medium border", selected ? "bg-accent-solid text-white border-accent-solid" : "bg-surface text-ink-2 border-line")}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                  {errors.allowed_days?.message && <p className="text-[11.5px] text-failure mt-1">{errors.allowed_days.message}</p>}
                </div>
              )}
            />
            <div className="grid grid-cols-2 gap-3">
              <Input label={t("policies.startHour")} type="number" min={0} max={23} {...form.register("allowed_start_hour", { valueAsNumber: true })} error={errors.allowed_start_hour?.message} />
              <Input label={t("policies.endHour")} type="number" min={0} max={23} {...form.register("allowed_end_hour", { valueAsNumber: true })} error={errors.allowed_end_hour?.message} />
            </div>
          </>
        ) : (
          <Input label={t("policies.pattern")} {...form.register("repository_pattern")} placeholder="prod-" error={errors.repository_pattern?.message} required />
        )}

        <Button type="submit" isLoading={create.isPending} className="w-full">{t("common.create")}</Button>
      </form>
    </Modal>
  );
}
