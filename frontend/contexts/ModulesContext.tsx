"use client";

import { createContext, useCallback, useContext, useMemo } from "react";
import { useModulesQuery, type ModuleInfo } from "@/lib/api";

export type { ModuleInfo };

interface ModulesContextValue {
  modules: ModuleInfo[];
  isLoading: boolean;
  /** Un module absent du registre est traité comme actif : fail-open sur l'affichage seulement, le backend tranche l'accès réel. */
  isActive: (key: string) => boolean;
  refresh: () => Promise<unknown>;
}

const ModulesContext = createContext<ModulesContextValue | undefined>(undefined);

export function ModulesProvider({ children }: { children: React.ReactNode }) {
  const { data, isLoading, refetch } = useModulesQuery();
  const modules = useMemo(() => data ?? [], [data]);

  const isActive = useCallback(
    (key: string) => {
      const entry = modules.find((m) => m.key === key);
      return entry ? entry.is_active : true;
    },
    [modules]
  );

  return (
    <ModulesContext.Provider value={{ modules, isLoading, isActive, refresh: refetch }}>{children}</ModulesContext.Provider>
  );
}

export function useModules(): ModulesContextValue {
  const ctx = useContext(ModulesContext);
  if (!ctx) {
    throw new Error("useModules doit être utilisé à l'intérieur d'un <ModulesProvider>.");
  }
  return ctx;
}
