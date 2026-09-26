"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { Lock, LogIn, User } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useT } from "@/lib/i18n";
import { HadiLogo } from "@/components/HadiLogo";
import { Input } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";

const schema = z.object({ username: z.string().trim().min(1), password: z.string().min(1), rememberMe: z.boolean() });

export default function LoginPage() {
  const t = useT();
  const router = useRouter();
  const { login } = useAuth();
  // La politique de l'instance décide si l'option est proposée : 0 jour la retire.
  const { data: policy } = useQuery({
    queryKey: ["session-policy"],
    queryFn: async () => (await api.get<{ remember_me_days: number }>("/api/auth/session-policy")).data,
    staleTime: Infinity,
    retry: false,
  });
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { username: "", password: "", rememberMe: false } });
  const signIn = useMutation({
    mutationFn: ({ username, password, rememberMe }: z.infer<typeof schema>) => login(username, password, rememberMe),
    onSuccess: (authUser) => router.push(authUser.must_change_password ? "/change-password" : "/dashboard"),
  });

  return (
    <main className="min-h-screen bg-page flex items-center justify-center p-4">
      <div className="max-w-[380px] w-full">
        <div className="flex flex-col items-center text-center mb-6 text-ink">
          <HadiLogo size={44} />
          <h1 className="text-2xl font-semibold tracking-tight leading-none mt-4">Hadi</h1>
          <p className="text-[12px] text-ink-3 mt-2">{t("app.tagline")}</p>
        </div>

        <form onSubmit={form.handleSubmit((values) => signIn.mutate(values))} className="space-y-4">
          {/* Un seul message, volontairement générique : ne pas dire si c'est le compte ou le mot de passe qui est faux. */}
          {signIn.isError && <Alert>{t("login.error")}</Alert>}
          <Input label={t("login.username")} icon={User} {...form.register("username")} required autoFocus autoComplete="username" />
          <Input label={t("login.password")} icon={Lock} type="password" {...form.register("password")} required autoComplete="current-password" />
          {(policy?.remember_me_days ?? 0) > 0 && (
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" {...form.register("rememberMe")} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-[13px] text-ink-2">{t("login.rememberMe")}</span>
            </label>
          )}
          <Button type="submit" icon={LogIn} isLoading={signIn.isPending} className="w-full mt-2">{t("login.submit")}</Button>
        </form>

        <p className="text-center text-xs text-ink-3 mt-8 leading-relaxed">
          {t("login.firstLogin")} <span className="font-mono">admin</span> / <span className="font-mono">admin</span>
          <br />
          {t("login.firstLoginHint")}
        </p>
      </div>
    </main>
  );
}
