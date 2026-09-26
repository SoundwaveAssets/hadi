"use client";

import { Dialog } from "radix-ui";
import { X } from "lucide-react";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/cn";

const SIZE_CLASSES = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-xl",
  xl: "max-w-3xl",
};

/**
 * Boîte de dialogue, registre outil : en-tête sur une ligne séparé par un
 * filet, corps dense, angles peu arrondis. Le défilement vit sur le corps
 * seul, l'en-tête reste visible quand le formulaire est long. Piégeage du
 * focus, Échap et clic hors boîte : Radix.
 */
export function Modal({
  title,
  description,
  onClose,
  children,
  size = "sm",
}: {
  title: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
  size?: keyof typeof SIZE_CLASSES;
}) {
  const t = useT();
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        {/* bg-black et non bg-ink : une trame d'assombrissement reste sombre dans les deux thèmes. */}
        <Dialog.Overlay className="fixed inset-0 bg-black/55 z-50" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[calc(100%-2rem)]",
            "bg-surface rounded-md border border-line-2 shadow-xl max-h-[90vh] flex flex-col overflow-hidden focus:outline-none",
            SIZE_CLASSES[size]
          )}
        >
          <div className="flex items-start justify-between gap-4 px-4 py-3 border-b border-line flex-shrink-0">
            <div className="min-w-0">
              <Dialog.Title className="text-[14px] font-semibold text-ink leading-tight truncate">{title}</Dialog.Title>
              {description ? (
                <Dialog.Description className="text-[12px] text-ink-3 mt-0.5 leading-snug">{description}</Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">{title}</Dialog.Description>
              )}
            </div>
            <Dialog.Close className="p-1 -m-1 rounded text-ink-3 hover:text-ink hover:bg-surface-2 flex-shrink-0" aria-label={t("common.close")}>
              <X className="w-4 h-4" />
            </Dialog.Close>
          </div>
          <div className="px-4 py-4 overflow-y-auto">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
