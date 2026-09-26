import { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("bg-surface rounded-md border border-line", className)} {...props} />;
}

export function CardHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("px-4 min-h-10 py-2 border-b border-line flex items-center justify-between gap-3", className)}>
      <div className="min-w-0">
        <h3 className="text-[13px] font-semibold text-ink leading-tight">{title}</h3>
        {description && <p className="text-[12px] text-ink-3 mt-0.5 leading-snug">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-1.5 flex-shrink-0">{actions}</div>}
    </div>
  );
}
