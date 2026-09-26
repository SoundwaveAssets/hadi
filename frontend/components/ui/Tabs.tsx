"use client";

import { Tabs as RadixTabs } from "radix-ui";
import { cn } from "@/lib/cn";

/** Barre d'onglets ; navigation aux flèches et rôles ARIA par Radix. Le contenu reste à la charge de la page. */
export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: string; label: string; icon?: React.ComponentType<{ className?: string }> }[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <RadixTabs.Root value={active} onValueChange={onChange}>
      <RadixTabs.List className="border-b border-line flex gap-1 overflow-x-auto">
        {tabs.map(({ key, label, icon: Icon }) => (
          <RadixTabs.Trigger
            key={key}
            value={key}
            className={cn(
              "inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors",
              "border-transparent text-ink-3 hover:text-ink-2 hover:border-line-2",
              "data-[state=active]:border-accent data-[state=active]:text-accent"
            )}
          >
            {Icon && <Icon className="w-4 h-4" />}
            {label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
    </RadixTabs.Root>
  );
}
