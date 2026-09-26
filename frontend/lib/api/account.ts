/** Compte connecté, assistant d'installation, exports et CLI. */
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, download } from "./client";
import type { TestResult } from "./types";

// --- compte ----------------------------------------------------------------------
export const updateEmail = (email: string | null) => api.patch("/api/auth/me", { email });

export const useChangePassword = () =>
  useMutation({ mutationFn: (payload: { current_password: string; new_password: string }) => api.post("/api/auth/change-password", payload) });

export type CliOs = "windows" | "linux" | "macos";
const CLI_FILENAMES: Record<CliOs, string> = { windows: "hadi.exe", linux: "hadi", macos: "hadi" };

export const downloadCli = (os: CliOs) => download("/api/cli/download", CLI_FILENAMES[os], { os, t: Date.now() });

/** Empreinte de l'exécutable servi : de quoi vérifier ce qu'on vient de télécharger. */
export interface CliChecksum {
  os: string;
  filename: string;
  sha256: string;
  size: number;
  modified: string;
  command: string;
}

export const useCliChecksum = (os: CliOs) =>
  useQuery({
    queryKey: ["cli-checksum", os],
    queryFn: async () => (await api.get<CliChecksum>("/api/cli/checksum", { params: { os } })).data,
    retry: false, // binaire non produit sur ce serveur : inutile d'insister
  });

// --- exports (module Rapports) ----------------------------------------------------
export type ReportKind = "pipelines.csv" | "audit.csv" | "summary.pdf";

export const downloadReport = (kind: ReportKind, from: string, to: string) =>
  download(`/api/reports/${kind}`, `${kind.replace(".", `_${from}_${to}.`)}`, { from, to });

// --- assistant d'installation -----------------------------------------------------
export interface SetupStatus {
  db_connected: boolean;
  setup_step: "database" | "integrations" | "done";
  setup_locked: boolean;
}

export const useSetupStatus = () =>
  useQuery({ queryKey: ["setup-status"], queryFn: async () => (await api.get<SetupStatus>("/api/setup/status")).data, staleTime: 0 });

export const setupDatabase = (payload: { db_host: string; db_port: number; db_name: string; db_user: string; db_password: string }) =>
  api.post("/api/setup/database", payload);

export const setupIntegrations = (payload: Record<string, string | null>) => api.post("/api/setup/integrations", payload);

export const setupTestTool = async (tool: string, url: string) =>
  (await api.post<TestResult>(`/api/setup/integrations/test/${tool}`, { url })).data;

export const completeSetup = () => api.post("/api/setup/complete");
