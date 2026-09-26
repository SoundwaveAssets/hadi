import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "./client";
import type { PipelineConfig } from "./types";

const base = "/api/pipeline-configs";
const key = ["pipeline-configs"] as const;

/** Champs modifiables ; `webhook_secret` en clair uniquement à la création ou pour le remplacer. */
export type PipelineConfigInput = Partial<Omit<PipelineConfig, "id" | "created_by" | "webhook_secret">> & { webhook_secret?: string };

export const usePipelineConfigs = () => useQuery({ queryKey: key, queryFn: async () => (await api.get<PipelineConfig[]>(base)).data });

function useConfigsMutation<TVariables, TResult>(run: (variables: TVariables) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: run, onSuccess: () => queryClient.invalidateQueries({ queryKey: key }) });
}

export interface CreatedPipelineConfig extends PipelineConfig {
  /** Étapes d'auto-provisionnement (Jenkins, SonarQube, Argo CD) qui ont échoué, sans bloquer l'enregistrement. */
  warnings: string[];
}

export const useCreatePipelineConfig = () =>
  useConfigsMutation(async (payload: PipelineConfigInput) => (await api.post<CreatedPipelineConfig>(base, payload)).data);

export const useUpdatePipelineConfig = () =>
  useConfigsMutation(async ({ id, ...patch }: PipelineConfigInput & { id: number }) => (await api.patch<PipelineConfig>(`${base}/${id}`, patch)).data);

export const useDeletePipelineConfig = () => useConfigsMutation((id: number) => api.delete(`${base}/${id}`));

export const downloadScaffold = (config: PipelineConfig, kind: "jenkinsfile" | "application-yaml") =>
  download(`${base}/${config.id}/${kind}`, kind === "jenkinsfile" ? "Jenkinsfile" : "application.yaml");
