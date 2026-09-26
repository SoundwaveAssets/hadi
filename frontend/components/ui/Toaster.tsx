"use client";

import { Toaster as Sonner } from "sonner";
import { useTheme } from "@/contexts/ThemeContext";

/** Retours d'action (enregistré, erreur...) : un seul endroit, à la place des bandeaux par page. */
export function Toaster() {
  const { resolvedTheme } = useTheme();
  return <Sonner theme={resolvedTheme} position="bottom-right" richColors closeButton duration={3500} />;
}
