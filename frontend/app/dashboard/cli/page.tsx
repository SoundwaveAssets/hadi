"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, Copy, Download } from "lucide-react";
import { downloadCli, useCliChecksum, type CliOs } from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import { useFormatDate } from "@/lib/format";
import { extractError } from "@/lib/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Field";

const PLATEFORMES: CliOs[] = ["windows", "linux", "macos"];

/** Plateforme du navigateur : proposée par défaut, l'administrateur peut en choisir une autre. */
function currentOs(): CliOs {
  const platform = typeof navigator === "undefined" ? "" : navigator.platform;
  return /win/i.test(platform) ? "windows" : /mac/i.test(platform) ? "macos" : "linux";
}

/**
 * Distribution du client en ligne de commande : le binaire par plateforme,
 * son empreinte, et de quoi démarrer. Séparé du profil, qui ne concerne que
 * le compte de la personne connectée.
 */
export default function CliPage() {
  const t = useT();
  const [os, setOs] = useState<CliOs>(currentOs);
  const download = useMutation({
    mutationFn: () => downloadCli(os),
    onError: (err) => toast.error(extractError(err, t("profile.cliError"))),
  });

  const apiUrl = typeof window !== "undefined" ? `${window.location.origin}/api` : "";

  return (
    <div className="space-y-4">
      <PageHeader title={t("page.cli")} />

      <Card>
        <CardHeader title={t("cli.download")} />
        <div className="p-4 space-y-4">
          <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
            <Select label={t("cli.platform")} value={os} onChange={(e) => setOs(e.target.value as CliOs)} className="sm:w-56">
              {PLATEFORMES.map((key) => (
                <option key={key} value={key}>{t(`cli.os.${key}` as MessageKey)}</option>
              ))}
            </Select>
            <Button type="button" variant="secondary" icon={Download} isLoading={download.isPending} onClick={() => download.mutate()}>
              {t("profile.downloadCli")}
            </Button>
          </div>
          <Checksum os={os} />
        </div>
      </Card>

      <Card>
        <CardHeader title={t("cli.start")} />
        <div className="p-4 space-y-3">
          <pre className="font-mono text-[12px] text-ink-2 bg-surface-2 border border-line rounded px-3 py-2 overflow-x-auto">
{`hadi config --api-url ${apiUrl}
hadi login
hadi pipelines`}
          </pre>
        </div>
      </Card>
    </div>
  );
}

/**
 * Empreinte du binaire servi par CETTE instance : la seule façon, pour qui
 * télécharge, de distinguer le fichier produit ici d'un fichier substitué en
 * chemin. Elle accompagne le téléchargement, c'est là qu'elle sert.
 */
function Checksum({ os }: { os: CliOs }) {
  const t = useT();
  const { dateTime } = useFormatDate();
  const [copied, setCopied] = useState(false);
  const { data, isError } = useCliChecksum(os);

  if (isError) return <p className="text-xs text-ink-3">{t("profile.cliChecksumMissing")}</p>;
  if (!data) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data.sha256);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="space-y-1.5 border-t border-line pt-3.5">
      <div className="flex items-center gap-2 flex-wrap">
        <p className="text-xs text-ink-3 uppercase tracking-wide">{t("profile.cliChecksum")}</p>
        <button type="button" onClick={copy} className="inline-flex items-center gap-1 text-xs text-accent hover:text-accent-hover">
          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copied ? t("common.copied") : t("common.copy")}
        </button>
        <span className="text-xs text-ink-3">{t("cli.built", { date: dateTime(data.modified) })}</span>
      </div>
      <code className="block font-mono text-[11px] text-ink-2 bg-surface-2 border border-line rounded px-3 py-2 break-all">{data.sha256}</code>
      <p className="text-xs text-ink-3">
        {t("profile.cliChecksumHint")} <code className="font-mono text-[11px]">{data.command}</code>
      </p>
    </div>
  );
}
