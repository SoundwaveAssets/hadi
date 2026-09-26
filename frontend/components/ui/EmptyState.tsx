import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  tone = "neutral",
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  tone?: "neutral" | "brand";
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center text-center py-16 px-6", className)}>
      <div
        className={cn(
          "p-3 rounded-full mb-3",
          tone === "brand" ? "bg-accent-soft text-accent" : "bg-surface-2 text-ink-3"
        )}
      >
        <Icon className="w-6 h-6" />
      </div>
      <h4 className="font-semibold text-ink">{title}</h4>
      {description && <p className="text-ink-2 mt-1.5 max-w-md text-sm">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
