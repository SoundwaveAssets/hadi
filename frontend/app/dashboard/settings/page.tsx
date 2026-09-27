"use client";

import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { SECURITY_CRITERIA, useAnomalyScores, useDatabaseSettings, useSaveConfig, useSaveDatabase, useToolConfig, type SecurityCriterion } from "@/lib/api";
import { extractError } from "@/lib/errors";
import { useT, type MessageKey } from "@/lib/i18n";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input, Select } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { Switch } from "@/components/ui/Switch";

export default function SettingsPage() {
  const t = useT();
  return (
    <div className="space-y-4">
      <PageHeader title={t("page.settings")} />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
        <div className="space-y-4">
          <SecurityCriterionCard />
          <ThresholdsCard />
        </div>
        <div className="space-y-4">
          <AiEngineCard />
          <DatabaseCard />
        </div>
      </div>
    </div>
  );
}

function AiEngineCard() {
  const t = useT();
  const { data: config } = useToolConfig();
  const save = useSaveConfig();
  const observation = config?.ai_observation_mode ?? true;

  const toggle = () =>
    save.mutate(
      { ai_observation_mode: !observation },
      { onSuccess: () => toast.success(t("settings.ai.saved")), onError: (err) => toast.error(extractError(err, t("settings.ai.saveError"))) }
    );

  return (
    <Card>
      <CardHeader title={t("settings.ai.title")} />
      <div className="p-4 flex items-center justify-between gap-4">
        <span className="text-[13px] text-ink-2">{t("settings.ai.observation")}</span>
        <Switch checked={observation} onChange={toggle} disabled={save.isPending} label={t("settings.ai.observation")} />
      </div>
    </Card>
  );
}

/**
 * Sur quoi le moteur juge la sécurité d'un commit. Réglage global : chaque
 * pipeline peut le surcharger depuis sa fiche (page Dépôts suivis).
 */
function SecurityCriterionCard() {
  const t = useT();
  const { data: config } = useToolConfig();
  const save = useSaveConfig();
  const current = config?.security_criterion ?? "new_code";

  const change = (value: SecurityCriterion) =>
    save.mutate(
      { security_criterion: value },
      { onSuccess: () => toast.success(t("settings.security.saved")), onError: (err) => toast.error(extractError(err, t("common.saveError"))) }
    );

  return (
    <Card>
      <CardHeader title={t("settings.security.title")} />
      <div className="p-4 space-y-3">
        <Select value={current} onChange={(e) => change(e.target.value as SecurityCriterion)} disabled={save.isPending}>
          {SECURITY_CRITERIA.map((key) => (
            <option key={key} value={key}>{t(`settings.security.${key}` as MessageKey)}</option>
          ))}
        </Select>
      </div>
    </Card>
  );
}

const thresholdsSchema = z
  .object({ review: z.number().min(0).max(1), block: z.number().min(0).max(1) })
  .refine((v) => v.review <= v.block, { path: ["review"], message: "review>block" });

type Thresholds = z.infer<typeof thresholdsSchema>;

function ThresholdsCard() {
  const t = useT();
  const { data: config } = useToolConfig();
  const { data: distribution } = useAnomalyScores();
  const scores = distribution?.scores ?? [];
  const save = useSaveConfig();

  const form = useForm<Thresholds>({
    resolver: zodResolver(thresholdsSchema),
    values: { review: config?.anomaly_review_threshold ?? 0.5, block: config?.anomaly_block_threshold ?? 0.8 },
  });
  const watched = useWatch({ control: form.control });
  const review = watched.review ?? 0.5;
  const block = watched.block ?? 0.8;

  // Les deux seuils restent ordonnés en glissant l'un vers l'autre.
  const setReview = (v: number) => { form.setValue("review", v); if (v > block) form.setValue("block", v); };
  const setBlock = (v: number) => { form.setValue("block", v); if (v < review) form.setValue("review", v); };

  const total = scores.length;
  const aboveReview = scores.filter((v) => v >= review).length;
  const aboveBlock = scores.filter((v) => v >= block).length;
  const pct = (n: number) => (total ? Math.round((n / total) * 100) : 0);

  const submit = form.handleSubmit((values) =>
    save.mutate(
      { anomaly_review_threshold: values.review, anomaly_block_threshold: values.block },
      { onSuccess: () => toast.success(t("settings.thresholds.saved")), onError: (err) => toast.error(extractError(err, t("settings.thresholds.saveError"))) }
    )
  );

  return (
    <Card>
      <CardHeader title={t("settings.thresholds.title")} />
      <form onSubmit={submit} className="p-4 space-y-4">
        <p className="text-[12.5px] text-ink-2 max-w-[70ch]">{t("settings.thresholds.explain")}</p>
        <ScoreHistogram scores={scores} review={review} block={block} />
        <p className="text-[11.5px] text-ink-3">
          {total
            ? t("settings.thresholds.impact", { total, waiting: aboveReview, blocked: aboveBlock })
            : t("settings.thresholds.noScores")}
          {distribution?.unscored ? ` ${t("settings.thresholds.unscored", { n: distribution.unscored })}` : ""}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ThresholdSlider
            label={t("settings.thresholds.review")}
            value={review}
            onChange={setReview}
            note={total ? t("settings.thresholds.reviewNote", { n: aboveReview, total, pct: pct(aboveReview) }) : t("settings.thresholds.noScores")}
          />
          <ThresholdSlider
            label={t("settings.thresholds.block")}
            value={block}
            onChange={setBlock}
            note={total ? t("settings.thresholds.blockNote", { n: aboveBlock, total, pct: pct(aboveBlock) }) : t("settings.thresholds.blockHint")}
          />
        </div>
        <Button type="submit" size="sm" icon={Save} isLoading={save.isPending}>{t("common.save")}</Button>
      </form>
    </Card>
  );
}

/** Trait vertical d'un seuil, avec son étiquette : sans elle, deux pointillés ne disent rien. */
function Marker({ x, label, tone, anchor }: { x: number; label: string; tone: string; anchor: "start" | "end" }) {
  const W = 600;
  return (
    <g>
      <line x1={x * W} x2={x * W} y1={TOP} y2={TOP + 72} stroke={tone} strokeWidth={1.5} strokeDasharray="3 2" />
      <text x={x * W + (anchor === "start" ? 3 : -3)} y={TOP - 3} textAnchor={anchor} fontSize={9} fill={tone}>
        {label} {Math.round(x * 100)} %
      </text>
    </g>
  );
}

const TOP = 14; // place pour les étiquettes de seuil au-dessus des barres

function ScoreHistogram({ scores, review, block }: { scores: number[]; review: number; block: number }) {
  const t = useT();
  const BINS = 20;
  const W = 600;
  const H = 72;
  const counts = new Array<number>(BINS).fill(0);
  for (const v of scores) counts[Math.min(BINS - 1, Math.floor(v * BINS))]++;
  const max = Math.max(1, ...counts);
  const bw = W / BINS;

  if (scores.length === 0) {
    return <div className="h-[72px] rounded border border-dashed border-line flex items-center justify-center text-[12px] text-ink-3">{t("settings.thresholds.noScores")}</div>;
  }

  return (
    <svg viewBox={`0 0 ${W} ${H + 30}`} className="w-full h-auto" role="img" aria-label={t("settings.thresholds.histogram")}>
      {/* Chaque barre : combien de pushs passés ont obtenu ce score. */}
      {counts.map((c, i) => {
        const lo = i / BINS;
        const tone = lo >= block ? "var(--color-failure)" : lo >= review ? "var(--color-unstable)" : "var(--color-line-2)";
        return <rect key={i} x={i * bw + 1} y={TOP + H - (c / max) * H} width={bw - 2} height={(c / max) * H} fill={tone} />;
      })}
      <Marker x={review} label={t("settings.thresholds.reviewShort")} tone="var(--color-unstable)" anchor={review > 0.75 ? "end" : "start"} />
      <Marker x={block} label={t("settings.thresholds.blockShort")} tone="var(--color-failure)" anchor={block > 0.75 ? "end" : "start"} />
      <text x={0} y={TOP - 3} fontSize={9} fill="var(--color-ink-3)">{t("settings.thresholds.axisY", { max })}</text>
      {[0, 0.25, 0.5, 0.75, 1].map((v) => (
        <text key={v} x={v * W} y={TOP + H + 11} textAnchor={v === 0 ? "start" : v === 1 ? "end" : "middle"} fontSize={9} fill="var(--color-ink-3)" fontFamily="var(--font-mono)">
          {Math.round(v * 100)} %
        </text>
      ))}
      <text x={W / 2} y={TOP + H + 24} textAnchor="middle" fontSize={9} fill="var(--color-ink-3)">{t("settings.thresholds.axisX")}</text>
    </svg>
  );
}

function ThresholdSlider({ label, value, onChange, note }: { label: string; value: number; onChange: (v: number) => void; note: string }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-[12.5px] font-medium text-ink-2">{label}</label>
        <span className="font-mono text-[12.5px] text-ink tabular-nums">{Math.round(value * 100)} %</span>
      </div>
      <input type="range" min={0} max={1} step={0.01} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-accent" />
      <p className="text-[11.5px] text-ink-3 mt-1">{note}</p>
    </div>
  );
}

const databaseSchema = z.object({
  db_host: z.string().trim().min(1),
  db_port: z.number().int().min(1).max(65535),
  db_name: z.string().trim().min(1),
  db_user: z.string().trim().min(1),
  db_password: z.string().min(1),
});

type DatabaseForm = z.infer<typeof databaseSchema>;

function DatabaseCard() {
  const t = useT();
  const { data: current } = useDatabaseSettings();
  const save = useSaveDatabase();
  const form = useForm<DatabaseForm>({
    resolver: zodResolver(databaseSchema),
    values: { db_host: current?.host ?? "", db_port: current?.port ?? 5432, db_name: current?.dbname ?? "", db_user: current?.user ?? "", db_password: "" },
  });
  const { errors } = form.formState;

  const submit = form.handleSubmit((values) =>
    save.mutate(values, {
      onSuccess: () => { toast.success(t("settings.db.saved")); form.resetField("db_password"); },
      onError: (err) => toast.error(extractError(err, t("settings.db.saveError"))),
    })
  );

  if (current?.from_environment) {
    return (
      <Card>
        <CardHeader title={t("settings.db.title")} />
        <div className="p-4 space-y-2 text-[13px]">
          <p className="text-ink-2">{t("settings.db.fromEnvironment")}</p>
          <p className="font-mono text-ink-3">
            {current.user}@{current.host}:{current.port}/{current.dbname}
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader title={t("settings.db.title")} />
      <form onSubmit={submit} className="p-4 space-y-3">
        <div className="grid grid-cols-[1fr_9ch] gap-3">
          <Input label={t("settings.db.host")} {...form.register("db_host")} error={errors.db_host?.message} mono required />
          <Input label={t("settings.db.port")} type="number" {...form.register("db_port", { valueAsNumber: true })} error={errors.db_port?.message} mono required />
        </div>
        <Input label={t("settings.db.name")} {...form.register("db_name")} error={errors.db_name?.message} mono required />
        <div className="grid grid-cols-2 gap-3">
          <Input label={t("settings.db.user")} {...form.register("db_user")} error={errors.db_user?.message} mono required />
          <Input label={t("settings.db.password")} type="password" {...form.register("db_password")} error={errors.db_password?.message} required />
        </div>
        <Button type="submit" size="sm" variant="secondary" icon={Save} isLoading={save.isPending}>{t("settings.db.submit")}</Button>
      </form>
    </Card>
  );
}
