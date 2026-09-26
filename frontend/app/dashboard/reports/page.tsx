"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { format, subDays } from "date-fns";
import { toast } from "sonner";
import { Download, FileBarChart, FileSpreadsheet, FileText } from "lucide-react";
import { downloadReport, type ReportKind } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { extractError } from "@/lib/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";

const EXPORTS: { kind: ReportKind; icon: typeof FileText; title: "reports.pipelinesCsv" | "reports.auditCsv" | "reports.summaryPdf"; hint: "reports.pipelinesCsvHint" | "reports.auditCsvHint" | "reports.summaryPdfHint" }[] = [
  { kind: "pipelines.csv", icon: FileSpreadsheet, title: "reports.pipelinesCsv", hint: "reports.pipelinesCsvHint" },
  { kind: "audit.csv", icon: FileText, title: "reports.auditCsv", hint: "reports.auditCsvHint" },
  { kind: "summary.pdf", icon: FileBarChart, title: "reports.summaryPdf", hint: "reports.summaryPdfHint" },
];

export default function ReportsPage() {
  const t = useT();
  const [from, setFrom] = useState(format(subDays(new Date(), 30), "yyyy-MM-dd"));
  const [to, setTo] = useState(format(new Date(), "yyyy-MM-dd"));
  const download = useMutation({
    mutationFn: (kind: ReportKind) => downloadReport(kind, from, to),
    onError: (err) => toast.error(extractError(err, t("reports.exportError"))),
  });

  return (
    <div className="space-y-4 pb-6">
      <PageHeader title={t("page.reports")} />

      <Card className="p-4">
        <div className="grid grid-cols-2 gap-3">
          <Input label={t("reports.from")} type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
          <Input label={t("reports.to")} type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} />
        </div>
      </Card>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {EXPORTS.map(({ kind, icon: Icon, title, hint }) => (
          <Card key={kind} className="p-5 flex flex-col gap-3">
            <div className="p-2.5 rounded-md bg-accent-soft text-accent w-fit">
              <Icon className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-ink">{t(title)}</h4>
              <p className="text-xs text-ink-3 mt-1">{t(hint)}</p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              icon={Download}
              onClick={() => download.mutate(kind)}
              isLoading={download.isPending && download.variables === kind}
              className="mt-auto"
            >
              {t("common.export")}
            </Button>
          </Card>
        ))}
      </div>
    </div>
  );
}
