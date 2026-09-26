/** Utilisateurs, jetons API, modules, politiques de conformité, notifications, journal d'audit. */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { AdminEvent, ApiToken, AuditEntry, ChainVerification, CompliancePolicy, Forge, ForgeIdentity, ModuleInfo, NotificationConfig, User, UserRole } from "./types";

/** Une mutation qui recharge les clés listées une fois terminée. */
function useInvalidating<TVariables, TResult = unknown>(keys: readonly string[], run: (variables: TVariables) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: () => keys.forEach((key) => queryClient.invalidateQueries({ queryKey: [key] })),
  });
}

// --- utilisateurs -------------------------------------------------------------
export const useUsers = () => useQuery({ queryKey: ["users"], queryFn: async () => (await api.get<User[]>("/api/users")).data });

export const useCreateUser = () =>
  useInvalidating(["users"], (payload: { username: string; email: string | null; password: string; role: UserRole }) => api.post<User>("/api/users", payload));

export const useUpdateUser = () =>
  useInvalidating(["users"], ({ id, ...patch }: { id: number; role?: UserRole; is_active?: boolean }) => api.patch<User>(`/api/users/${id}`, patch));

export const useResetPassword = () =>
  useInvalidating(["users"], ({ id, new_password }: { id: number; new_password: string }) => api.post(`/api/users/${id}/reset-password`, { new_password }));

// --- identités de forge -----------------------------------------------------------
const identitiesKey = (userId: number) => ["forge-identities", userId] as const;

export const useIdentities = (userId: number) =>
  useQuery({ queryKey: identitiesKey(userId), queryFn: async () => (await api.get<ForgeIdentity[]>(`/api/users/${userId}/identities`)).data });

export const useAddIdentity = (userId: number) =>
  useInvalidating(["forge-identities"], (payload: { provider: Forge; login: string; external_id?: string }) => api.post<ForgeIdentity>(`/api/users/${userId}/identities`, payload));

export const useRemoveIdentity = (userId: number) =>
  useInvalidating(["forge-identities"], (identityId: number) => api.delete(`/api/users/${userId}/identities/${identityId}`));

// --- jetons API -----------------------------------------------------------------
export const useApiTokens = () => useQuery({ queryKey: ["api-tokens"], queryFn: async () => (await api.get<ApiToken[]>("/api/api-tokens")).data });

export interface CreatedToken extends ApiToken {
  token: string;
}

export const useCreateToken = () =>
  useInvalidating(["api-tokens"], async (payload: { name: string; role: UserRole; expires_in_days?: number }) => (await api.post<CreatedToken>("/api/api-tokens", payload)).data);

export const useRevokeToken = () => useInvalidating(["api-tokens"], (id: number) => api.post(`/api/api-tokens/${id}/revoke`));

// --- modules ----------------------------------------------------------------------
export const useModulesQuery = () => useQuery({ queryKey: ["modules"], queryFn: async () => (await api.get<ModuleInfo[]>("/api/modules")).data, staleTime: 60_000 });

export const useToggleModule = () => useInvalidating(["modules"], (key: string) => api.post(`/api/modules/${key}/toggle`));

// --- politiques de conformité ----------------------------------------------------
export const usePolicies = () => useQuery({ queryKey: ["compliance-policies"], queryFn: async () => (await api.get<CompliancePolicy[]>("/api/compliance-policies")).data });

export const useCreatePolicy = () =>
  useInvalidating(["compliance-policies"], (payload: Omit<CompliancePolicy, "id" | "created_by" | "is_active">) => api.post("/api/compliance-policies", { ...payload, is_active: true, created_by: "" }));

export const useTogglePolicy = () => useInvalidating(["compliance-policies"], (id: number) => api.post(`/api/compliance-policies/${id}/toggle`));

export const useDeletePolicy = () => useInvalidating(["compliance-policies"], (id: number) => api.delete(`/api/compliance-policies/${id}`));

// --- notifications -------------------------------------------------------------
export const useNotificationConfig = () =>
  useQuery({ queryKey: ["notification-config"], queryFn: async () => (await api.get<NotificationConfig>("/api/notifications/config")).data });

/** Le mot de passe SMTP ne s'envoie qu'en clair et seulement pour le remplacer. */
export type NotificationConfigInput = Omit<NotificationConfig, "smtp_password"> & { smtp_password?: string };

export const useSaveNotificationConfig = () =>
  useInvalidating(["notification-config"], (payload: NotificationConfigInput) => api.post("/api/notifications/config", payload));

export const sendTestEmail = async (to: string) => (await api.post<{ message?: string }>("/api/notifications/test", { to })).data;

// --- journal d'audit ---------------------------------------------------------------
export interface AuditFilters {
  limit?: number;
  offset?: number;
  decision?: string;
  repository?: string;
  developer?: string;
}

export const useAudit = (filters: AuditFilters) =>
  useQuery({
    queryKey: ["audit", filters],
    queryFn: async () => (await api.get<{ entries: AuditEntry[]; total: number }>("/api/audit", { params: filters })).data,
    placeholderData: keepPreviousData, // la page précédente reste affichée pendant le chargement de la suivante
  });

export const verifyAuditChain = async () => (await api.get<ChainVerification>("/api/audit/verify")).data;

// --- journal des actions d'administration -----------------------------------------
export interface AdminEventFilters {
  limit?: number;
  offset?: number;
  actor?: string;
  /** Préfixe : `user.` renvoie toutes les actions sur les comptes. */
  action?: string;
  target_type?: string;
}

export const useAdminEvents = (filters: AdminEventFilters) =>
  useQuery({
    queryKey: ["admin-events", filters],
    queryFn: async () => (await api.get<{ entries: AdminEvent[]; total: number }>("/api/audit/admin-events", { params: filters })).data,
    placeholderData: keepPreviousData,
  });

export const verifyAdminEvents = async () => (await api.get<ChainVerification>("/api/audit/admin-events/verify")).data;
