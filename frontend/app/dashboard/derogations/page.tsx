"use client";

import { FileClock, ShieldCheck } from "lucide-react";
import { useDerogations } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useFormatDate } from "@/lib/format";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { CenteredSpinner } from "@/components/ui/Spinner";

export default function DerogationsPage() {
  const t = useT();
  const { dateTime } = useFormatDate();
  const { data: entries = [], isLoading } = useDerogations();

  return (
    <div className="space-y-4">
      <PageHeader title={t("page.derogations")} />
      <Card className="overflow-hidden">
        {isLoading ? (
          <CenteredSpinner className="py-12" />
        ) : entries.length === 0 ? (
          <EmptyState icon={FileClock} title={t("derogations.empty")} />
        ) : (
          <ul className="divide-y divide-line">
            {entries.map((e) => (
              <li key={e.id} className="p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-ink">{e.repository_name}</span>
                  <span className="text-xs text-ink-3">{dateTime(e.timestamp)}</span>
                </div>
                <p className="text-sm text-ink-3 mt-1">{t("derogations.pushBy")} {e.developer_username}</p>
                <p className="flex items-center gap-1.5 text-sm text-ink-2 mt-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-good flex-shrink-0" />
                  {t("derogations.approvedBy")} <span className="font-medium text-ink-2">{e.approved_by ?? "-"}</span>{t("derogations.confirmedBy")}{" "}
                  <span className="font-medium text-ink-2">{e.four_eyes_approved_by ?? "-"}</span>
                </p>
                <p className="text-sm text-ink-2 mt-1.5">{e.justification}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
