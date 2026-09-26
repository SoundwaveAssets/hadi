"use client";

import { Moon, Sun, SunMoon } from "lucide-react";
import { useTheme, type Theme } from "@/contexts/ThemeContext";
import { IconButton } from "@/components/ui/IconButton";
import { useT, type MessageKey } from "@/lib/i18n";

const NEXT: Record<Theme, Theme> = { light: "dark", dark: "system", system: "light" };

const CONFIG: Record<Theme, { icon: typeof Sun; label: MessageKey }> = {
  light: { icon: Sun, label: "theme.toDark" },
  dark: { icon: Moon, label: "theme.toSystem" },
  system: { icon: SunMoon, label: "theme.toLight" },
};

/** Un seul bouton qui fait défiler clair → sombre → automatique → clair, pas
 *  de menu déroulant pour un réglage aussi simple à 3 états. */
export function ThemeToggle() {
  const t = useT();
  const { theme, setTheme } = useTheme();
  const { icon, label } = CONFIG[theme];

  return <IconButton icon={icon} label={t(label)} onClick={() => setTheme(NEXT[theme])} />;
}
