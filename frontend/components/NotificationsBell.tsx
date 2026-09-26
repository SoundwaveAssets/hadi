"use client";

import { useT } from "@/lib/i18n";
import { useQuery } from "@tanstack/react-query";
import { Bell, Clock, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { Menu } from "@/components/ui/Menu";
import { EmptyState } from "@/components/ui/EmptyState";
import type { UserRole } from "@/contexts/AuthContext";

interface PendingEntry {
  id: number;
  repository_name: string;
  decision: string;
  timestamp: string;
}

const POLL_INTERVAL_MS = 30_000;

/** File des pipelines nécessitant une action, visible seulement par les rôles qui peuvent agir dessus. */
export function NotificationsBell({ role, onNavigate }: { role: UserRole; onNavigate: (href: string) => void }) {
  const t = useT();
  const canSeePending = role === "admin" || role === "security_officer";
  const { data: entries = [] } = useQuery({
    queryKey: ["pending", ""],
    queryFn: async () => (await api.get<PendingEntry[]>("/api/decisions/pending")).data,
    enabled: canSeePending,
    refetchInterval: POLL_INTERVAL_MS,
  });

  if (!canSeePending) return null;

  return (
    <Menu
      trigger={({ onClick }) => (
        <button
          onClick={onClick}
          className="relative p-2 rounded-lg text-ink-3 hover:text-ink-2 hover:bg-surface-2 transition-colors"
          aria-label={t("notif.label")}
        >
          <Bell className="w-5 h-5" />
          {entries.length > 0 && (
            <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-critical-solid text-white text-[10px] font-semibold">
              {entries.length > 9 ? "9+" : entries.length}
            </span>
          )}
        </button>
      )}
    >
      <div className="px-3.5 py-2 border-b border-line">
        <p className="text-sm font-semibold text-ink">{t("notif.title")}</p>
      </div>
      {entries.length === 0 ? (
        <EmptyState icon={Bell} title={t("notif.empty")} description={t("notif.emptyHint")} className="py-8" />
      ) : (
        <div className="max-h-80 overflow-y-auto">
          {entries.slice(0, 8).map((e) => (
            <button
              key={e.id}
              onClick={() => onNavigate("/dashboard/decisions")}
              className="w-full flex items-start gap-2.5 px-3.5 py-2.5 text-left hover:bg-surface-2 transition-colors"
            >
              {e.decision === "BLOCKED" ? (
                <ShieldAlert className="w-4 h-4 text-critical flex-shrink-0 mt-0.5" />
              ) : (
                <Clock className="w-4 h-4 text-warning flex-shrink-0 mt-0.5" />
              )}
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink-2 truncate">{e.repository_name}</p>
                <p className="text-xs text-ink-3">{e.decision}</p>
              </div>
            </button>
          ))}
        </div>
      )}
      <div className="px-3.5 pt-2 border-t border-line">
        <button
          onClick={() => onNavigate("/dashboard/decisions")}
          className="text-xs font-medium text-accent hover:text-accent-hover py-1.5"
        >
          {t("notif.seeAll")}
        </button>
      </div>
    </Menu>
  );
}
