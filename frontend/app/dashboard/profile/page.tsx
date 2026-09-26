"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
import { CalendarDays, KeyRound, Mail, Save, ShieldCheck, User as UserIcon } from "lucide-react";
import Link from "next/link";
import { updateEmail } from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import { extractError } from "@/lib/errors";
import { useFormatDate } from "@/lib/format";
import { useAuth } from "@/contexts/AuthContext";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";

const emailSchema = z.object({ email: z.string().trim().email().or(z.literal("")) });

export default function ProfilePage() {
  const t = useT();
  const { user, refreshUser } = useAuth();
  const { longDate } = useFormatDate();

  const form = useForm<z.infer<typeof emailSchema>>({ resolver: zodResolver(emailSchema), values: { email: user?.email ?? "" } });
  const saveEmail = useMutation({
    mutationFn: ({ email }: { email: string }) => updateEmail(email || null),
    onSuccess: async () => { await refreshUser(); toast.success(t("profile.saved")); },
    onError: (err) => toast.error(extractError(err, t("profile.saveError"))),
  });

  if (!user) return null;

  return (
    <div className="space-y-4">
      <PageHeader title={t("page.profile")} />

      <Card className="p-4">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-full bg-ink text-page flex items-center justify-center text-xl font-semibold flex-shrink-0">
            {user.username.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <h3 className="text-lg font-semibold text-ink">{user.username}</h3>
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-accent-hover bg-accent-soft border border-accent/30 px-2.5 py-1 rounded-full mt-1.5">
              <ShieldCheck className="w-3.5 h-3.5" /> {t(`role.${user.role}` as MessageKey)}
            </span>
          </div>
        </div>
        {user.created_at && (
          <div className="flex items-center gap-2 text-sm text-ink-3 mt-5 pt-5 border-t border-line">
            <CalendarDays className="w-4 h-4 text-ink-3" />
            {t("profile.since")} {longDate(user.created_at)}
          </div>
        )}
      </Card>

      <Card className="p-4 space-y-4">
        <SectionTitle icon={UserIcon}>{t("profile.account")}</SectionTitle>
        <form onSubmit={form.handleSubmit((values) => saveEmail.mutate(values))} className="space-y-4">
          <Input label={t("login.username")} value={user.username} disabled hint={t("profile.usernameLocked")} />
          <Input label={t("common.email")} type="email" icon={Mail} {...form.register("email")} placeholder="vous@exemple.org" error={form.formState.errors.email?.message} />
          <Button type="submit" icon={Save} isLoading={saveEmail.isPending}>{t("common.save")}</Button>
        </form>
      </Card>


      <Card className="p-4 space-y-3">
        <SectionTitle icon={KeyRound}>{t("pipeline.security")}</SectionTitle>
        <Link href="/change-password">
          <Button type="button" variant="secondary" icon={KeyRound}>{t("user.changePassword")}</Button>
        </Link>
      </Card>
    </div>
  );
}

function SectionTitle({ icon: Icon, children }: { icon: React.ComponentType<{ className?: string }>; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="p-2 rounded bg-surface-2 text-ink-2">
        <Icon className="w-4 h-4" />
      </div>
      <h3 className="text-sm font-semibold text-ink">{children}</h3>
    </div>
  );
}
