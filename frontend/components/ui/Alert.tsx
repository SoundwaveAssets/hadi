import { AlertTriangle, CheckCircle2, Info, XCircle, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

type Tone = "error" | "success" | "warning" | "info";

// Icône dans la teinte du ton, texte en encre neutre : les teintes de statut
// (voir StatusBadge) ne tiennent pas 4.5:1 de contraste en tant que texte sur
// un fond aussi clair que leur propre pastille, seule l'icône porte la
// couleur, le message reste toujours lisible.
const TONE_META: Record<Tone, { icon: LucideIcon; wrap: string; icon_cls: string }> = {
  error: { icon: XCircle, wrap: "bg-critical-soft border-critical/20", icon_cls: "text-critical" },
  success: { icon: CheckCircle2, wrap: "bg-good-soft border-good/20", icon_cls: "text-good" },
  warning: { icon: AlertTriangle, wrap: "bg-warning-soft border-warning/30", icon_cls: "text-warning" },
  info: { icon: Info, wrap: "bg-accent-soft border-accent/20", icon_cls: "text-accent" },
};

export function Alert({ tone = "error", children, className }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  const meta = TONE_META[tone];
  const Icon = meta.icon;
  return (
    <div className={cn("p-3.5 rounded-xl border flex items-start gap-2.5 text-sm", meta.wrap, className)}>
      <Icon className={cn("w-4 h-4 flex-shrink-0 mt-0.5", meta.icon_cls)} />
      <span className="font-medium text-ink">{children}</span>
    </div>
  );
}
