"use client";

import { ButtonHTMLAttributes, forwardRef } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: LucideIcon;
  /** Pas de texte visible sur ce bouton : le libellé sert à la fois d'accessibilité et d'infobulle native. */
  label: string;
  danger?: boolean;
}

/** Bouton compact icône seule pour une rangée d'actions de tableau, évite le menu déroulant caché quand 2-4 actions tiennent très bien affichées directement. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ icon: Icon, label, danger, className, disabled, ...props }, ref) => (
    <button
      ref={ref}
      aria-label={label}
      title={label}
      disabled={disabled}
      className={cn(
        "p-1.5 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
        danger ? "text-ink-3 hover:text-critical hover:bg-critical-soft" : "text-ink-3 hover:text-ink-2 hover:bg-surface-2",
        className
      )}
      {...props}
    >
      <Icon className="w-4 h-4" />
    </button>
  )
);
IconButton.displayName = "IconButton";
