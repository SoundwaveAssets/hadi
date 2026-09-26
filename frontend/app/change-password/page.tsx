"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, KeyRound, ShieldCheck } from "lucide-react";
import { useChangePassword } from "@/lib/api";
import { extractError } from "@/lib/errors";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/lib/i18n";
import { Input } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";

const MIN_LENGTH = 12;

export default function ChangePasswordPage() {
  const router = useRouter();
  const { user, refreshUser } = useAuth();
  const t = useT();
  const isForced = user?.must_change_password ?? false;

  const schema = z
    .object({
      current_password: z.string().min(1),
      new_password: z.string().min(MIN_LENGTH, t("password.newHint", { n: MIN_LENGTH })),
      confirm: z.string(),
    })
    .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: t("password.mismatch") });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { current_password: "", new_password: "", confirm: "" },
  });
  const { errors } = form.formState;
  const change = useChangePassword();

  const submit = form.handleSubmit(({ current_password, new_password }) =>
    change.mutate(
      { current_password, new_password },
      {
        onSuccess: async () => {
          await refreshUser();
          router.push("/dashboard");
        },
        onError: (err) => toast.error(extractError(err, t("password.error"))),
      }
    )
  );

  return (
    <main className="min-h-screen bg-page flex items-center justify-center p-4">
      <div className="max-w-sm w-full">
        {!isForced && (
          <Link href="/dashboard" className="inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink-2 mb-4">
            <ArrowLeft className="w-4 h-4" /> {t("password.backToDashboard")}
          </Link>
        )}

        <div className="bg-surface rounded-md shadow-sm border border-line p-8">
          <div className="flex flex-col items-center text-center mb-6">
            <div className={`w-11 h-11 rounded-md flex items-center justify-center mb-4 border ${isForced ? "bg-warning-soft border-warning/30" : "bg-accent-soft border-accent/20"}`}>
              <ShieldCheck className={`w-5 h-5 ${isForced ? "text-warning" : "text-accent"}`} />
            </div>
            <h1 className="font-serif text-lg font-semibold text-ink">{isForced ? t("password.forcedTitle") : t("password.title")}</h1>
            <p className="text-ink-3 text-sm mt-1.5">{isForced ? t("password.forcedHint") : t("password.hint")}</p>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <Input label={t("password.current")} type="password" {...form.register("current_password")} error={errors.current_password?.message} required autoFocus />
            <Input
              label={t("password.new")}
              hint={t("password.newHint", { n: MIN_LENGTH })}
              type="password"
              {...form.register("new_password")}
              error={errors.new_password?.message}
              required
            />
            <Input label={t("password.confirm")} type="password" {...form.register("confirm")} error={errors.confirm?.message} required />
            <Button type="submit" icon={KeyRound} isLoading={change.isPending} className="w-full mt-2">
              {t("password.submit")}
            </Button>
          </form>
        </div>
      </div>
    </main>
  );
}
