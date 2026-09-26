"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { ArrowLeft, Loader2, RotateCcw, ScrollText, ShieldAlert, Terminal } from "lucide-react";
import { pipelinePace, useCommitHistory, usePipeline, usePipelineLogs, useRequestDerogation, useRetrigger, useStages, type AuditEntry, type Pipeline, type SonarMetrics, type Stage } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useFormatDate } from "@/lib/format";
import { extractError } from "@/lib/errors";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { StatusBadge } from "@/components/StatusBadge";
import { Card, CardHeader } from "@/components/ui/Card";
import { LogConsole } from "@/components/devtools/LogConsole";
import { PipelineView, type Stage as PipelineStage } from "@/components/devtools/PipelineView";

/** Un pipeline figé ou en échec se relance ; un pipeline en cours ou déployé, non. */
const RETRIGGERABLE_STATUSES = new Set(["BLOCKED", "ANALYSIS_FAILED", "DEPLOY_FAILED", "WAITING_HUMAN"]);

const RATING_TONE: Record<string, string> = {
  A: "text-good bg-good-soft",
  B: "text-good bg-good-soft",
  C: "text-warning bg-warning-soft",
  D: "text-serious bg-serious-soft",
  E: "text-critical bg-critical-soft",
};

function RatingChip({ label, rating }: { label: string; rating: string | null | undefined }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className={`w-9 h-9 rounded flex items-center justify-center font-bold text-sm ${
          rating ? RATING_TONE[rating] : "text-ink-3 bg-surface-2"
        }`}
      >
        {rating ?? "-"}
      </div>
      <span className="text-xs text-ink-3 text-center">{label}</span>
    </div>
  );
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="w-9 h-9 rounded flex items-center justify-center font-semibold text-xs text-ink-2 bg-surface-2">
        {value}
      </div>
      <span className="text-xs text-ink-3 text-center">{label}</span>
    </div>
  );
}

/**
 * Le déploiement (sync Argo CD) n'est pas une étape du Jenkinsfile, il se
 * déclenche après, depuis l'Orchestrateur lui-même, mais visuellement, c'est
 * la suite logique de la frise : on le synthétise depuis le statut du pipeline.
 * Un pipeline bloqué ou en attente donne une étape « interrompue », pas « en
 * attente » : ce déploiement n'aura pas lieu tant qu'une décision ne le permet pas.
 */
/** Décisions sur lesquelles un développeur peut demander une dérogation. */
const ACTIONABLE_DECISIONS = new Set(["WAITING_HUMAN", "BLOCKED"]);

/**
 * Demande de dérogation par le développeur concerné.
 *
 * L'action existait dans l'API et dans la CLI, jamais dans l'interface : un
 * développeur bloqué devait ouvrir un terminal pour demander un examen. Elle
 * ne débloque rien par elle-même — deux administrateurs restent nécessaires —,
 * elle fait entrer le pipeline dans la file de décision avec un motif écrit.
 */
function DerogationRequest({ pipeline, history }: { pipeline: Pipeline; history: AuditEntry[] }) {
  const t = useT();
  const { user } = useAuth();
  const demander = useRequestDerogation();
  const [ouvert, setOuvert] = useState(false);
  const [motif, setMotif] = useState("");

  const dernière = history[history.length - 1];
  const actionnable = dernière && ACTIONABLE_DECISIONS.has(dernière.decision);
  const concerné = user?.username === pipeline.author;
  if (!actionnable || !concerné) return null;

  const envoyer = () =>
    demander.mutate(
      { id: dernière.id, justification: motif },
      {
        onSuccess: () => {
          setOuvert(false);
          setMotif("");
          toast.success(t("pipeline.derogationRequested"));
        },
        onError: (err) => toast.error(extractError(err, t("pipeline.derogationError"))),
      }
    );

  return (
    <>
      <Button size="sm" variant="secondary" icon={ShieldAlert} onClick={() => setOuvert(true)}>
        {t("pipeline.requestDerogation")}
      </Button>
      {ouvert && (
        <Modal title={t("pipeline.requestDerogation")} onClose={() => setOuvert(false)} size="md">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (motif.trim()) envoyer();
            }}
            className="space-y-3.5"
          >
            <p className="text-[12.5px] text-ink-2">{t("pipeline.derogationExplain")}</p>
            <Input label={t("common.justification")} value={motif} onChange={(e) => setMotif(e.target.value)} autoFocus />
            <div className="flex gap-2 justify-end">
              <Button type="button" variant="secondary" onClick={() => setOuvert(false)}>{t("common.cancel")}</Button>
              <Button type="submit" disabled={!motif.trim()} isLoading={demander.isPending}>{t("common.confirm")}</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

/**
 * Relance l'analyse complète sur le même commit. Pensé pour un échec
 * d'infrastructure — agent Jenkins sans réseau, service externe momentanément
 * injoignable — qui n'a rien à voir avec le code : repousser un commit vide
 * pour redéclencher une analyse n'est pas une réponse acceptable.
 *
 * Proposé seulement quand il y a quelque chose à relancer : un pipeline en
 * cours ou déjà déployé n'a pas à l'être.
 */
function RetriggerButton({ pipeline }: { pipeline: Pipeline }) {
  const t = useT();
  const retrigger = useRetrigger();
  const { user } = useAuth();

  const relançable = RETRIGGERABLE_STATUSES.has(pipeline.status);
  const autorisé = user?.role !== "developer" || pipeline.author === user?.username;
  if (!relançable || !autorisé) return null;

  return (
    <Button
      size="sm"
      variant="secondary"
      icon={RotateCcw}
      isLoading={retrigger.isPending}
      onClick={() =>
        retrigger.mutate(pipeline.id, {
          onSuccess: (data) => toast.success(data.message || t("pipeline.retriggered")),
          onError: (err) => toast.error(extractError(err, t("pipeline.retriggerError"))),
        })
      }
    >
      {t("pipeline.retrigger")}
    </Button>
  );
}

function deploymentStage(pipelineStatus: string, name: string): PipelineStage {
  const STATUS_MAP: Record<string, string> = {
    DEPLOYING: "IN_PROGRESS",
    DEPLOYED: "SUCCESS",
    DEPLOY_FAILED: "FAILED",
    BLOCKED: "ABORTED",
    WAITING_HUMAN: "ABORTED",
    DEROGATION_PENDING: "ABORTED",
  };
  return { name, status: STATUS_MAP[pipelineStatus] ?? "NOT_EXECUTED", durationMs: null };
}

function toPipelineStages(stages: Stage[]): PipelineStage[] {
  return stages.map((s) => ({ name: s.name, status: s.status, durationMs: s.duration_ms }));
}


export default function PipelineDetailPage() {
  const t = useT();
  const params = useParams();
  const id = params.id as string;

  const fmt = useFormatDate();

  const { data: pipeline = null, isLoading } = usePipeline(Number(id));
  // Même cadence que le pipeline lui-même : soutenue pendant l'exécution,
  // ralentie dès qu'on attend une décision humaine, arrêtée à la fin.
  const pace = pipelinePace(pipeline?.status);
  const { data: history = [] } = useCommitHistory(pipeline?.commit_id, { pace });
  const { data: logs = null } = usePipelineLogs(Number(id), { enabled: Boolean(pipeline), pace });
  // Les étapes ont leur propre requête, bien plus légère que la console :
  // c'est elle qui est sondée de près pendant l'exécution.
  const { data: live = null } = useStages(Number(id), { enabled: Boolean(pipeline), pace });
  const stages = live?.stages ?? logs?.stages ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 text-accent animate-spin" />
      </div>
    );
  }

  if (!pipeline) {
    return (
      <div className="text-center py-12">
        <p className="text-ink-3">{t("pipeline.notFound")}</p>
        <Link href="/dashboard/pipelines" className="text-accent hover:text-accent-hover text-sm font-medium mt-3 inline-block">
          {t("pipeline.back")}
        </Link>
      </div>
    );
  }

  // Instantané SonarQube le plus récent disponible dans l'historique de ce
  // commit, absent des décisions plus anciennes (champ introduit après coup).
  let sonarMetrics: SonarMetrics | null = null;
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].sonarqube_metrics) {
      try {
        sonarMetrics = JSON.parse(history[i].sonarqube_metrics as string);
      } catch {
        sonarMetrics = null;
      }
      break;
    }
  }

  return (
    <div className="space-y-4">
      <Link
        href="/dashboard/pipelines"
        className="inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink-2"
      >
        <ArrowLeft className="w-4 h-4" /> {t("pipeline.back")}
      </Link>

      <Card className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-ink">{pipeline.repository}</h2>
            <p className="text-ink-3 text-sm mt-1">
              {pipeline.branch} · <span className="font-mono">{pipeline.commit_id.slice(0, 12)}</span> ·{" "}
              {pipeline.author}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={pipeline.status} />
            <RetriggerButton pipeline={pipeline} />
            <DerogationRequest pipeline={pipeline} history={history} />
          </div>
        </div>
        {/* Première ligne seulement, comme sur GitHub/GitLab/Gitea, un
            message de commit détaillé sur plusieurs paragraphes ne doit pas
            faire exploser cette carte. Le texte complet reste consultable
            via l'infobulle native (title). */}
        <p className="text-ink-2 text-sm mt-4 truncate" title={pipeline.commit_message}>
          {pipeline.commit_message.split("\n")[0]}
        </p>
        <p className="text-ink-3 text-xs mt-2">{t("pipeline.receivedAt")} {fmt.dateTime(pipeline.created_at)}</p>
      </Card>

      {/* Timeline des décisions */}
      <Card>
        <CardHeader title={t("page.decisions")} />
        <div className="p-4">
          {history.length === 0 ? (
            <p className="text-sm text-ink-3">{t("overview.noDecisions")}</p>
          ) : (
            <ul className="space-y-4">
              {history.map((entry) => (
                <li key={entry.id} className="border-l-2 border-line pl-4">
                  <div className="flex items-center gap-2 flex-wrap">
                    <StatusBadge status={entry.decision} />
                    <span className="text-xs text-ink-3">{fmt.dateTime(entry.timestamp)}</span>
                  </div>
                  <p className="text-sm text-ink-2 mt-1.5">{entry.justification}</p>
                  <p className="text-xs text-ink-3 mt-1">
                    {t("pipeline.score")} {entry.ai_anomaly_score ?? "-"} {t("decisions.vulnsLabel")} {entry.sonarqube_vulnerabilities ?? "-"}
                    {entry.approved_by && ` · ${t("pipeline.approvedBy", { name: entry.approved_by })}`}
                    {entry.four_eyes_approved_by && ` · ${t("pipeline.confirmedBy", { name: entry.four_eyes_approved_by })}`}
                  </p>
                  {entry.ai_explanation && (
                    <p className="text-xs text-ink-3 mt-1">{t("decisions.explanation")} {entry.ai_explanation}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      {/* Journaux d'exécution */}
      <Card>
        <CardHeader title={t("pipeline.logs")} />
        <div className="p-4 space-y-4">
          {stages.length > 0 && (
            <div>
              <p className="text-xs font-medium text-ink-3 uppercase tracking-wide mb-2">{t("pipeline.stagesTitle")}</p>
              <PipelineView stages={[...toPipelineStages(stages), deploymentStage(pipeline.status, t("pipeline.stage.deploy"))]} />
            </div>
          )}

          {sonarMetrics && (
            <div className="border-t border-line pt-4">
              <p className="text-xs font-medium text-ink-3 uppercase tracking-wide mb-3">{t("pipeline.quality")}</p>
              <div className="flex flex-wrap justify-center gap-4">
                <RatingChip label={t("pipeline.security")} rating={sonarMetrics.security_rating} />
                <RatingChip label={t("pipeline.reliability")} rating={sonarMetrics.reliability_rating} />
                <RatingChip label={t("pipeline.maintainability")} rating={sonarMetrics.maintainability_rating} />
                <StatChip label={t("pipeline.vulnerabilities")} value={sonarMetrics.vulnerabilities?.toString() ?? "-"} />
                <StatChip label={t("pipeline.bugs")} value={sonarMetrics.bugs?.toString() ?? "-"} />
                <StatChip
                  label={t("pipeline.hotspots")}
                  value={sonarMetrics.security_hotspots_reviewed != null ? `${sonarMetrics.security_hotspots_reviewed}%` : "-"}
                />
                <StatChip label={t("pipeline.coverage")} value={sonarMetrics.coverage != null ? `${sonarMetrics.coverage}%` : "-"} />
                <StatChip
                  label={t("pipeline.duplication")}
                  value={sonarMetrics.duplicated_lines_density != null ? `${sonarMetrics.duplicated_lines_density}%` : "-"}
                />
                <StatChip
                  label={t("pipeline.loc")}
                  value={sonarMetrics.lines_of_code != null ? fmt.number(sonarMetrics.lines_of_code) : "-"}
                />
              </div>
            </div>
          )}

          <div>
            <p className="text-xs font-medium text-ink-3 uppercase tracking-wide mb-1.5 flex items-center gap-1.5">
              <ScrollText className="w-3.5 h-3.5" /> {t("pipeline.internalLog")}
            </p>
            <LogConsole
              title="hadi"
              content={logs?.execution_log}
              maxHeight={260}
              emptyMessage={t("pipeline.internalLogEmpty")}
            />
          </div>

          <div>
            <p className="text-xs font-medium text-ink-3 uppercase tracking-wide mb-1.5 flex items-center gap-1.5">
              <Terminal className="w-3.5 h-3.5" /> {t("pipeline.jenkinsConsole")}
            </p>
            <LogConsole
              title={pipeline.jenkins_build_number ? `jenkins · build #${pipeline.jenkins_build_number}` : "jenkins"}
              content={logs?.jenkins_console}
              maxHeight={520}
              emptyMessage={t("pipeline.consoleEmpty")}
            />
          </div>

          {logs?.notes && logs.notes.length > 0 && (
            <div className="space-y-1">
              {logs.notes.map((note, i) => (
                <p key={i} className="text-xs text-ink-3">
                  {note}
                </p>
              ))}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
