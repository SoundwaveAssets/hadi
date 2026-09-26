"use client";

import { useState } from "react";
import { Popover } from "radix-ui";
import Link from "next/link";
import { cn } from "@/lib/cn";

/**
 * Panneau déroulant ancré à un déclencheur : menu utilisateur, notifications,
 * sélecteur de dépôt, liste d'un Select. Positionnement, portail, clic
 * extérieur, Échap et focus : Radix Popover. Un clic dans le panneau le
 * referme (comportement de menu).
 */
// Angles peu arrondis et ombre courte : registre d'outil, pas de carte flottante.
const PANEL_CLASSES = "min-w-48 bg-surface rounded-md border border-line-2 shadow-md py-1 z-[100] focus:outline-none";

export function Menu({
  trigger,
  children,
  align = "right",
  fullWidth = false,
}: {
  /** `onClick` est sans effet (Radix gère l'ouverture) ; conservé pour les déclencheurs existants. */
  trigger: (props: { onClick: () => void; isOpen: boolean }) => React.ReactNode;
  children: React.ReactNode;
  align?: "left" | "right";
  /** Champ de formulaire : le panneau prend la largeur du déclencheur. */
  fullWidth?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <Popover.Root open={isOpen} onOpenChange={setIsOpen}>
      <Popover.Trigger asChild>
        <span className={fullWidth ? "flex w-full" : "inline-flex"}>{trigger({ onClick: () => undefined, isOpen })}</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align={fullWidth ? "start" : align === "right" ? "end" : "start"}
          sideOffset={fullWidth ? 4 : 6}
          className={PANEL_CLASSES}
          style={fullWidth ? { width: "var(--radix-popover-trigger-width)" } : undefined}
          onClick={() => setIsOpen(false)}
        >
          {children}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

type MenuItemProps = {
  icon?: React.ComponentType<{ className?: string }>;
  danger?: boolean;
  href?: string;
  children: React.ReactNode;
};

export function MenuItem({ icon: Icon, children, danger, href, ...props }: MenuItemProps & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const className = cn(
    "w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-left transition-colors",
    danger ? "text-critical hover:bg-critical-soft" : "text-ink-2 hover:bg-surface-2"
  );

  if (href) {
    return (
      <Link href={href} className={className} {...(props as React.AnchorHTMLAttributes<HTMLAnchorElement>)}>
        {Icon && <Icon className="w-4 h-4" />}
        {children}
      </Link>
    );
  }

  return (
    <button className={className} {...props}>
      {Icon && <Icon className="w-4 h-4" />}
      {children}
    </button>
  );
}
