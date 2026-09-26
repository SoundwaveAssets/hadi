"use client";

import { createContext, useCallback, useContext, useSyncExternalStore } from "react";

export type Theme = "light" | "dark" | "system";

const STORAGE_KEY = "orchestrator_theme";

interface ThemeContextValue {
  /** Préférence enregistrée ; "system" suit prefers-color-scheme (voir globals.css). */
  theme: Theme;
  /** Thème réellement affiché à l'instant (résout "system"), pour l'icône du bouton. */
  resolvedTheme: "light" | "dark";
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

/*
 * Le thème est un état externe à React (localStorage + media query), lu via
 * useSyncExternalStore : le serveur rend "system", le client se resynchronise
 * à l'hydratation sans setState dans un effet.
 */
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

function subscribe(listener: () => void) {
  listeners.add(listener);
  const mql = window.matchMedia("(prefers-color-scheme: dark)");
  mql.addEventListener("change", listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    mql.removeEventListener("change", listener);
    window.removeEventListener("storage", listener);
  };
}

function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function readResolved(): "light" | "dark" {
  const theme = readTheme();
  if (theme !== "system") return theme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(subscribe, readTheme, () => "system" as Theme);
  const resolvedTheme = useSyncExternalStore(subscribe, readResolved, () => "light" as const);

  const setTheme = useCallback((next: Theme) => {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {}
    applyTheme(next);
    notify();
  }, []);

  return <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme doit être utilisé sous ThemeProvider.");
  return ctx;
}

/** Servi depuis public/theme-init.js (voir app/layout.tsx) : pose data-theme
 *  sur <html> avant tout rendu React, pour ne jamais afficher le mauvais
 *  thème l'espace d'une frame. Même clé de stockage que ci-dessus. */
export const THEME_STORAGE_KEY = STORAGE_KEY;
