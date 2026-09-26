"use client";

import { Switch as RadixSwitch } from "radix-ui";
import { cn } from "@/lib/cn";

/** Interrupteur on/off partagé (Modules, Politiques de conformité...). Clavier et ARIA par Radix. */
export function Switch({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <RadixSwitch.Root
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      aria-label={label}
      className={cn(
        "relative flex-shrink-0 w-11 h-6 rounded-full transition-colors disabled:opacity-50",
        "data-[state=checked]:bg-accent data-[state=unchecked]:bg-line-2"
      )}
    >
      <RadixSwitch.Thumb className="block w-5 h-5 rounded-full bg-surface shadow transition-transform translate-x-0.5 data-[state=checked]:translate-x-[22px]" />
    </RadixSwitch.Root>
  );
}
