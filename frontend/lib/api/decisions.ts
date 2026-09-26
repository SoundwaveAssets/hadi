import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { AuditEntry, DayActivity, Page, Pipeline, PipelineLogs, PipelineStages, Summary } from "./types";

const base = "/api/decisions";
const byRepo = (repository?: string) => (repository ? { repository } : {});

export const decisionKeys = {
  pipelines: (repository?: string, page?: number) => ["pipelines", repository ?? "", page ?? 0] as const,
  pipeline: (id: number) => ["pipeline", id] as const,
  logs: (id: number) => ["pipeline-logs", id] as const,
  stages: (id: number) => ["pipeline-stages", id] as const,
  history: (commit?: string) => ["history", commit ?? ""] as const,
  pending: (repository?: string) => ["pending", repository ?? ""] as const,
  derogations: ["derogations"] as const,
  repositories: ["repositories"] as const,
  overview: (repository?: string) => ["overview", repository ?? ""] as const,
};

/*
 * Cadences de sondage. Trois régimes, parce que les trois situations n'ont
 * rien à voir : une étape Jenkins qui tourne change en secondes, une file
 * d'attente humaine change en minutes, et un pipeline terminé ne change
 * plus jamais. Une cadence unique, c'est soit un écran en retard, soit
 * Jenkins interrogé pour rien pendant des heures.
 *
 * React Query suspend de lui-même ces intervalles quand l'onglet passe en
 * arrière-plan (refetchIntervalInBackground vaut false par défaut) : une
 * fenêtre que personne ne regarde ne fait travailler personne.
 */
const STAGES_INTERVAL_MS = 2_000;
const RUNNING_INTERVAL_MS = 5_000;
const WAITING_INTERVAL_MS = 20_000;
const LIST_INTERVAL_MS = 30_000;

/*
 * Même vocabulaire que l'API (app/domain/pipeline_status.py) et que la CLI :
 * un test de la suite compare les trois listes. DEROGATION_REQUESTED n'y
 * figure pas, c'est une décision d'audit, jamais un statut de pipeline.
 */
/** États définitifs : rien ne les fait plus évoluer, inutile de continuer à sonder. */
export const TERMINAL_STATUSES = new Set(["DEPLOYED", "DEPLOY_FAILED", "BLOCKED", "ANALYSIS_FAILED"]);

/** En attente d'un humain : plus rien ne bouge tant que personne n'a tranché. */
const AWAITING_HUMAN_STATUSES = new Set(["WAITING_HUMAN", "DEROGATION_PENDING"]);

/** Cadence due à un pipeline : travail en cours, attente d'un humain, ou plus rien. */
export function pipelinePace(status?: string): number | false {
  if (!status || TERMINAL_STATUSES.has(status)) return false;
  return AWAITING_HUMAN_STATUSES.has(status) ? WAITING_INTERVAL_MS : RUNNING_INTERVAL_MS;
}

/** Cadence d'une liste : soutenue tant qu'un pipeline travaille, lente sinon (un push peut arriver). */
const listPace = (statuses: string[]) =>
  statuses.some((status) => pipelinePace(status) === RUNNING_INTERVAL_MS) ? RUNNING_INTERVAL_MS : LIST_INTERVAL_MS;

export const usePipelines = (repository?: string, limit = 50, offset = 0) =>
  useQuery({
    queryKey: [...decisionKeys.pipelines(repository), limit, offset],
    queryFn: async () => (await api.get<Page<Pipeline>>(`${base}/pipelines`, { params: { ...byRepo(repository), limit, offset } })).data,
    refetchInterval: (q) => listPace((q.state.data?.items ?? []).map((p) => p.status)),
  });

/** Un pipeline, sondé tant qu'il n'a pas atteint un état définitif (voir pipelinePace). */
export const usePipeline = (id: number) =>
  useQuery({
    queryKey: decisionKeys.pipeline(id),
    queryFn: async () => (await api.get<Pipeline>(`${base}/pipelines/${id}`)).data,
    enabled: Number.isFinite(id),
    retry: false,
    refetchInterval: (q) => pipelinePace(q.state.data?.status),
  });

/**
 * Étapes du build, sondées toutes les 2 s pendant l'exécution : c'est la
 * seule requête assez légère pour ça (wfapi seul, pas la console), et c'est
 * elle qui fait avancer la frise sans décalage visible. Elle s'arrête dès
 * que le pipeline attend un humain ou qu'il est terminé.
 */
export const useStages = (id: number, options: { enabled?: boolean; pace?: number | false } = {}) =>
  useQuery({
    queryKey: decisionKeys.stages(id),
    queryFn: async () => (await api.get<PipelineStages>(`${base}/pipelines/${id}/stages`)).data,
    enabled: (options.enabled ?? true) && Number.isFinite(id),
    retry: false,
    refetchInterval: options.pace === RUNNING_INTERVAL_MS ? STAGES_INTERVAL_MS : (options.pace ?? false),
  });

/**
 * Journaux : console Jenkins (potentiellement volumineuse) et narration
 * interne. Cadence du pipeline, jamais celle des étapes.
 */
export const usePipelineLogs = (id: number, options: { enabled?: boolean; pace?: number | false } = {}) =>
  useQuery({
    queryKey: decisionKeys.logs(id),
    queryFn: async () => (await api.get<PipelineLogs>(`${base}/pipelines/${id}/logs`)).data,
    enabled: options.enabled ?? true,
    retry: false,
    refetchInterval: options.pace ?? false,
  });

export const useCommitHistory = (commit?: string, options: { pace?: number | false } = {}) =>
  useQuery({
    queryKey: decisionKeys.history(commit),
    queryFn: async () => (await api.get<AuditEntry[]>(`${base}/history/${commit}`)).data,
    enabled: Boolean(commit),
    retry: false,
    refetchInterval: options.pace ?? false,
  });

/*
 * File d'attente et dérogations : ce sont les écrans qu'un administrateur
 * laisse ouverts en attendant d'avoir quelque chose à valider. Un pipeline
 * qui bascule en attente doit y apparaître sans rechargement manuel.
 */
export const usePending = (repository?: string) =>
  useQuery({
    queryKey: decisionKeys.pending(repository),
    queryFn: async () => (await api.get<AuditEntry[]>(`${base}/pending`, { params: byRepo(repository) })).data,
    refetchInterval: WAITING_INTERVAL_MS,
  });

export const useDerogations = () =>
  useQuery({
    queryKey: decisionKeys.derogations,
    queryFn: async () => (await api.get<AuditEntry[]>(`${base}/derogations`)).data,
    refetchInterval: LIST_INTERVAL_MS,
  });

export const useRepositories = () =>
  useQuery({ queryKey: decisionKeys.repositories, queryFn: async () => (await api.get<{ repository: string }[]>(`${base}/repositories`)).data });

export const useOverview = (repository?: string) =>
  useQuery({
    queryKey: decisionKeys.overview(repository),
    queryFn: async () => {
      const params = byRepo(repository);
      const [summary, pipelines, activity] = await Promise.all([
        api.get<Summary>(`${base}/summary`, { params }),
        api.get<Page<Pipeline>>(`${base}/pipelines`, { params: { ...params, limit: 8 } }),
        api.get<DayActivity[]>(`${base}/activity`, { params: { ...params, days: 365 } }),
      ]);
      return { summary: summary.data, recent: pipelines.data.items, activity: activity.data };
    },
    refetchInterval: (q) => listPace((q.state.data?.recent ?? []).map((p) => p.status)),
  });

export interface ApproveResult {
  status: "success" | "pending_second_approval";
  message: string;
  audit_id: number;
}

/** Après toute action sur une décision, tout ce qui l'affiche est rechargé. */
function useDecisionMutation<TVariables, TResult>(run: (variables: TVariables) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      for (const key of ["pipelines", "pipeline", "pipeline-logs", "history", "pending", "derogations", "overview"]) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export const useApprove = () =>
  useDecisionMutation(async ({ id, justification }: { id: number; justification: string }) => (await api.post<ApproveResult>(`${base}/${id}/approve`, { justification })).data);

export const useRequestDerogation = () =>
  useDecisionMutation(async ({ id, justification }: { id: number; justification: string }) => (await api.post(`${base}/${id}/request-derogation`, { justification })).data);

export const useRetrigger = () =>
  useDecisionMutation(async (id: number) => (await api.post<{ message: string }>(`${base}/pipelines/${id}/retrigger`)).data);
