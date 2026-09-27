import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Forge, Health, JenkinsCredential, TestResult, ToolConfig, ToolKey } from "./types";

const base = "/api/config";

export const configKeys = {
  config: ["config"] as const,
  health: ["integrations-health"] as const,
  scores: ["anomaly-scores"] as const,
  database: ["database-settings"] as const,
  jenkinsCredentials: ["jenkins-credentials"] as const,
};

export const useToolConfig = () =>
  useQuery({ queryKey: configKeys.config, queryFn: async () => (await api.get<ToolConfig>(base)).data });

export const useIntegrationsHealth = (refetchInterval?: number) =>
  useQuery({ queryKey: configKeys.health, queryFn: async () => (await api.get<Health>(`${base}/health`)).data, refetchInterval });

/** Scores réellement calculés, plus le nombre de pushs restés sans mesure (historique insuffisant). */
export const useAnomalyScores = () =>
  useQuery({
    queryKey: configKeys.scores,
    queryFn: async () => (await api.get<{ scores: number[]; unscored: number }>(`${base}/anomaly-scores`)).data,
  });

export interface DatabaseSettings {
  host?: string;
  port?: number;
  user?: string;
  dbname?: string;
  /** La connexion vient de DB_HOST : la modifier ici n'aurait aucun effet. */
  from_environment?: boolean;
}

export const useDatabaseSettings = () =>
  useQuery({ queryKey: configKeys.database, queryFn: async () => (await api.get<DatabaseSettings>(`${base}/database`)).data });

export const useJenkinsCredentials = (enabled = true) =>
  useQuery({ queryKey: configKeys.jenkinsCredentials, queryFn: async () => (await api.get<JenkinsCredential[]>(`${base}/jenkins/credentials`)).data, enabled });

function useConfigMutation<TVariables>(run: (variables: TVariables) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: configKeys.config });
      queryClient.invalidateQueries({ queryKey: configKeys.health });
    },
  });
}

/** Réglages globaux (seuils, mode observation) : seuls les champs envoyés changent. */
export const useSaveConfig = () => useConfigMutation((patch: Partial<ToolConfig>) => api.post(base, patch));

export interface ToolCredentials {
  url: string;
  user?: string;
  token?: string;
}

export const useSaveTool = () =>
  useConfigMutation(({ tool, ...payload }: ToolCredentials & { tool: ToolKey }) =>
    api.post(isForge(tool) ? `${base}/forge/${tool}` : `${base}/${tool}`, payload)
  );

export const testTool = async (tool: ToolKey, payload: ToolCredentials) =>
  (await api.post<TestResult>(`${base}/test/${tool}`, payload)).data;

export const useSaveDatabase = () =>
  useConfigMutation((payload: { db_host: string; db_port: number; db_name: string; db_user: string; db_password: string }) => api.post(`${base}/database`, payload));

const FORGES: readonly string[] = ["gitea", "github", "gitlab"];
export const isForge = (tool: string): tool is Forge => FORGES.includes(tool);
