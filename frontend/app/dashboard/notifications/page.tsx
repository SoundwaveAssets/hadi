"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
import { Bell, Save, Send } from "lucide-react";
import { sendTestEmail, useNotificationConfig, useSaveNotificationConfig } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { extractError } from "@/lib/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";

const schema = z.object({
  smtp_host: z.string().trim(),
  smtp_port: z.number().int().min(1).max(65535),
  smtp_user: z.string().trim(),
  smtp_password: z.string(),
  smtp_use_tls: z.boolean(),
  from_address: z.string().trim().email().or(z.literal("")),
  notify_on_waiting_human: z.boolean(),
  notify_on_blocked: z.boolean(),
  notify_on_derogation: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

const EVENTS = ["notify_on_waiting_human", "notify_on_blocked", "notify_on_derogation"] as const;
const EVENT_LABELS = { notify_on_waiting_human: "notifications.onWaiting", notify_on_blocked: "notifications.onBlocked", notify_on_derogation: "notifications.onDerogation" } as const;

export default function NotificationsPage() {
  const t = useT();
  const { data: saved } = useNotificationConfig();
  const save = useSaveNotificationConfig();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    values: {
      smtp_host: saved?.smtp_host ?? "",
      smtp_port: saved?.smtp_port ?? 587,
      smtp_user: saved?.smtp_user ?? "",
      smtp_password: "",
      smtp_use_tls: saved?.smtp_use_tls ?? true,
      from_address: saved?.from_address ?? "",
      notify_on_waiting_human: saved?.notify_on_waiting_human ?? true,
      notify_on_blocked: saved?.notify_on_blocked ?? true,
      notify_on_derogation: saved?.notify_on_derogation ?? true,
    },
  });
  const { errors } = form.formState;

  const submit = form.handleSubmit(({ smtp_password, ...values }) =>
    // Mot de passe vide : celui déjà enregistré est conservé.
    save.mutate(smtp_password ? { ...values, smtp_password } : values, {
      onSuccess: () => { toast.success(t("common.savedOk")); form.resetField("smtp_password"); },
      onError: (err) => toast.error(extractError(err, t("common.saveError"))),
    })
  );

  return (
    <div className="space-y-4 pb-6">
      <PageHeader title={t("page.notifications")} />

      <Card className="p-4 space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-md bg-warning-soft text-warning">
            <Bell className="w-5 h-5" />
          </div>
          <h3 className="text-base font-semibold text-ink">{t("notifications.smtp")}</h3>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Input label={t("notifications.host")} {...form.register("smtp_host")} placeholder="smtp.exemple.org" error={errors.smtp_host?.message} />
            <Input label={t("common.port")} type="number" {...form.register("smtp_port", { valueAsNumber: true })} error={errors.smtp_port?.message} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input label={t("common.user")} {...form.register("smtp_user")} />
            <Input label={t("common.password")} type="password" {...form.register("smtp_password")} placeholder={t("integrations.keepSecret")} />
          </div>
          <Input label={t("notifications.from")} type="email" {...form.register("from_address")} placeholder="hadi@exemple.org" error={errors.from_address?.message} />
          <label className="flex items-center gap-2.5 text-sm text-ink-2">
            <input type="checkbox" {...form.register("smtp_use_tls")} className="w-4 h-4 rounded border-line-2 text-accent focus:ring-accent" />
            {t("notifications.starttls")}
          </label>

          <div className="border-t border-line pt-4 space-y-2.5">
            <p className="text-xs font-medium text-ink-3 uppercase tracking-wide">{t("notifications.events")}</p>
            {EVENTS.map((key) => (
              <label key={key} className="flex items-center gap-2.5 text-sm text-ink-2">
                <input type="checkbox" {...form.register(key)} className="w-4 h-4 rounded border-line-2 text-accent focus:ring-accent" />
                {t(EVENT_LABELS[key])}
              </label>
            ))}
          </div>

          <Button type="submit" icon={Save} isLoading={save.isPending}>{t("common.save")}</Button>
        </form>
      </Card>

      <TestEmailCard />
    </div>
  );
}

function TestEmailCard() {
  const t = useT();
  const form = useForm<{ to: string }>({ resolver: zodResolver(z.object({ to: z.string().trim().email() })), defaultValues: { to: "" } });
  const send = useMutation({
    mutationFn: ({ to }: { to: string }) => sendTestEmail(to),
    onSuccess: (data) => toast.success(data.message ?? t("common.send")),
    onError: (err) => toast.error(extractError(err, t("notifications.sendError"))),
  });

  return (
    <Card className="p-4 space-y-3">
      <h3 className="text-sm font-semibold text-ink">{t("notifications.sendTest")}</h3>
      <form onSubmit={form.handleSubmit((values) => send.mutate(values))} className="flex gap-2">
        <div className="flex-1">
          <Input type="email" {...form.register("to")} placeholder="vous@exemple.org" error={form.formState.errors.to?.message} />
        </div>
        <Button type="submit" variant="secondary" icon={Send} isLoading={send.isPending}>{t("common.send")}</Button>
      </form>
    </Card>
  );
}
