"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { CheckCircle2, ChevronRight, Database, KeyRound, Loader2, Server, ShieldCheck, Wrench } from "lucide-react";
import { completeSetup, SETUP_TOKEN_STORAGE_KEY, setupDatabase, useSetupStatus } from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import { extractError } from "@/lib/errors";
import { HadiLogo } from "@/components/HadiLogo";
import { Input } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

type StepId = "prerequisites" | "database" | "review";

const STEPS: { id: StepId; label: MessageKey }[] = [
  { id: "prerequisites", label: "setup.step.prerequisites" },
  { id: "database", label: "setup.step.database" },
  { id: "review", label: "setup.step.review" },
];

export default function SetupPage() {
  const t = useT();
  const router = useRouter();
  const { data: status, isLoading } = useSetupStatus();
  // L'assistant commence par les prérequis, y compris quand la pile fournit
  // déjà une base : sauter d'emblée au récapitulatif priverait l'administrateur
  // de ce qu'il doit avoir sous la main.
  const [chosen, setStep] = useState<StepId | null>(null);
  const step = chosen ?? "prerequisites";

  useEffect(() => {
    if (status?.setup_locked) router.push("/login");
  }, [status, router]);

  if (isLoading || status?.setup_locked) {
    return (
      <main className="min-h-screen bg-page flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-accent animate-spin" />
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-page flex items-center justify-center p-4 py-10">
      <div className="max-w-2xl w-full">
        <div className="flex flex-col items-center text-center mb-5 text-ink">
          <HadiLogo size={40} />
          <h1 className="text-2xl font-semibold tracking-tight mt-3">Hadi</h1>
          <p className="text-ink-2 text-sm mt-2">{t("setup.title")}</p>
        </div>

        <Stepper current={step} onSelect={setStep} />

        <div className="bg-surface rounded-md shadow-sm border border-line p-8 mt-6">
          {step === "prerequisites" && <PrerequisitesStep onNext={() => setStep("database")} />}
          {step === "database" && <DatabaseStep onNext={() => setStep("review")} dejaConnectee={status?.db_connected ?? false} />}
          {step === "review" && <ReviewStep onDone={() => router.push("/login")} />}
        </div>
      </div>
    </main>
  );
}

function Stepper({ current, onSelect }: { current: StepId; onSelect: (id: StepId) => void }) {
  const t = useT();
  const currentIndex = STEPS.findIndex((s) => s.id === current);
  return (
    <div className="flex items-center justify-between px-2">
      {STEPS.map((s, i) => {
        const isDone = i < currentIndex;
        const isActive = i === currentIndex;
        return (
          <div key={s.id} className="flex items-center flex-1 last:flex-none">
            <button type="button" onClick={() => onSelect(s.id)} className="flex flex-col items-center gap-1.5 cursor-pointer" aria-current={isActive}>
              <div
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold border-2 transition-colors",
                  isDone ? "bg-accent-solid border-accent-solid text-white" : isActive ? "border-accent text-accent bg-surface" : "border-line text-ink-3 bg-surface"
                )}
              >
                {isDone ? <CheckCircle2 className="w-4 h-4" /> : i + 1}
              </div>
              <span className={cn("text-xs font-medium", isActive ? "text-accent" : "text-ink-3")}>{t(s.label)}</span>
            </button>
            {i < STEPS.length - 1 && <div className={cn("h-0.5 flex-1 mx-2", isDone ? "bg-accent" : "bg-line")} />}
          </div>
        );
      })}
    </div>
  );
}

function StepHeader({ icon: Icon, title, description }: { icon: typeof Wrench; title: string; description?: string }) {
  return (
    <div className="flex items-start gap-3 mb-6 pb-4 border-b border-line">
      <div className="w-9 h-9 rounded-md bg-accent-soft text-accent flex items-center justify-center flex-shrink-0">
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <h2 className="font-semibold text-ink">{title}</h2>
        {description && <p className="text-sm text-ink-3 mt-0.5">{description}</p>}
      </div>
    </div>
  );
}

// --- Étape 0 : prérequis et jeton d'installation ---
function PrerequisitesStep({ onNext }: { onNext: () => void }) {
  const t = useT();
  const items: MessageKey[] = ["setup.req.postgres", "setup.req.tools", "setup.req.locked"];
  const form = useForm<{ token: string }>({
    resolver: zodResolver(z.object({ token: z.string().trim().min(1) })),
    defaultValues: { token: typeof window === "undefined" ? "" : window.sessionStorage.getItem(SETUP_TOKEN_STORAGE_KEY) ?? "" },
  });

  const start = form.handleSubmit(({ token }) => {
    window.sessionStorage.setItem(SETUP_TOKEN_STORAGE_KEY, token.trim());
    onNext();
  });

  return (
    <form onSubmit={start}>
      <StepHeader icon={Wrench} title={t("setup.before")} />
      <ul className="space-y-3 mb-6">
        {items.map((item) => (
          <li key={item} className="flex gap-3 text-sm text-ink-2">
            <CheckCircle2 className="w-4 h-4 text-accent flex-shrink-0 mt-0.5" />
            {t(item)}
          </li>
        ))}
      </ul>
      <Input label={t("setup.token")} {...form.register("token")} mono required autoFocus className="mb-6" />
      <Button type="submit" className="w-full" size="md">{t("setup.start")} <ChevronRight className="w-4 h-4" /></Button>
    </form>
  );
}

// --- Étape 1 : base de données ---
const databaseSchema = z.object({
  db_host: z.string().trim().min(1),
  db_port: z.number().int().min(1).max(65535),
  db_name: z.string().trim().min(1),
  db_user: z.string().trim().min(1),
  db_password: z.string().min(1),
});

function DatabaseStep({ onNext, dejaConnectee }: { onNext: () => void; dejaConnectee: boolean }) {
  const t = useT();
  const form = useForm<z.infer<typeof databaseSchema>>({
    resolver: zodResolver(databaseSchema),
    defaultValues: { db_host: "localhost", db_port: 5432, db_name: "orchestrator_db", db_user: "postgres", db_password: "" },
  });
  const { errors } = form.formState;
  const connect = useMutation({ mutationFn: setupDatabase, onSuccess: onNext, onError: (err) => toast.error(extractError(err, t("setup.dbError"))) });

  return (
    <form onSubmit={form.handleSubmit((values) => connect.mutate(values))}>
      <StepHeader icon={Database} title={t("setup.dbTitle")} />
      <div className="grid grid-cols-2 gap-4 mb-4">
        <Input label={t("settings.db.host")} icon={Server} {...form.register("db_host")} error={errors.db_host?.message} required />
        <Input label={t("common.port")} type="number" {...form.register("db_port", { valueAsNumber: true })} error={errors.db_port?.message} required />
      </div>
      <Input label={t("settings.db.name")} icon={Database} {...form.register("db_name")} error={errors.db_name?.message} required className="mb-4" />
      <div className="grid grid-cols-2 gap-4 mb-6">
        <Input label={t("common.user")} {...form.register("db_user")} error={errors.db_user?.message} required />
        <Input label={t("common.password")} icon={KeyRound} type="password" {...form.register("db_password")} error={errors.db_password?.message} required />
      </div>
      <Button type="submit" isLoading={connect.isPending} className="w-full">{t("setup.testContinue")} <ChevronRight className="w-4 h-4" /></Button>
      {dejaConnectee && (
        <>
          <p className="text-[12.5px] text-ink-3 mt-4 text-center">{t("setup.dbAlready")}</p>
          <Button type="button" variant="ghost" onClick={onNext} className="w-full mt-2">
            {t("setup.skip")} <ChevronRight className="w-4 h-4" />
          </Button>
        </>
      )}
    </form>
  );
}

// --- Étape 2 : intégrations ---

// --- Étape 3 : récapitulatif et verrouillage ---
function ReviewStep({ onDone }: { onDone: () => void }) {
  const t = useT();
  const complete = useMutation({ mutationFn: completeSetup, onSuccess: onDone, onError: (err) => toast.error(extractError(err, t("setup.completeError"))) });

  return (
    <div>
      <StepHeader icon={ShieldCheck} title={t("setup.step.review")} />
      <div className="bg-accent-soft border border-accent/20 rounded-md p-4 mb-6">
        <p className="text-sm font-medium text-ink mb-1">{t("setup.defaultAdmin")}</p>
        <p className="text-sm text-ink">
          <span className="font-mono bg-surface/60 px-1.5 py-0.5 rounded">admin</span> / <span className="font-mono bg-surface/60 px-1.5 py-0.5 rounded">admin</span> {t("setup.defaultAdminHint")}
        </p>
      </div>
      <div className="bg-warning-soft border border-warning/30 rounded-md p-4 mb-6">
        <p className="text-sm font-medium text-warning mb-1">{t("setup.nextStep")}</p>
        <p className="text-sm text-warning">{t("setup.nextStepHint")}</p>
      </div>
      <p className="text-sm text-ink-3 mb-6">{t("setup.lockWarning")}</p>
      <Button onClick={() => complete.mutate()} isLoading={complete.isPending} variant="dark" icon={ShieldCheck} className="w-full">{t("setup.lock")}</Button>
    </div>
  );
}
