"use client";

/**
 * Console de journal : la sortie brute d'un build, lisible comme dans un terminal.
 *
 * Toujours sombre, quel que soit le thème de la page, l'œil d'un développeur
 * est réglé sur un fond noir pour ce type de contenu. Numéros de ligne dans
 * une gouttière, police à chasse fixe, lignes d'erreur et d'avertissement
 * repérées d'un liseré, suivi automatique de la fin tant que l'utilisateur
 * n'a pas fait défiler vers le haut.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/cn";

const ERROR_PATTERN = /\b(error|erreur|fatal|exception|traceback|failed|échec|echec)\b/i;
const WARN_PATTERN = /\b(warn|warning|avertissement|deprecated|unstable)\b/i;

interface LogConsoleProps {
  content: string | string[] | null | undefined;
  title?: string;
  /** Suit la fin du journal quand de nouvelles lignes arrivent. */
  follow?: boolean;
  maxHeight?: number;
  emptyMessage?: string;
  className?: string;
}

export function LogConsole({
  content,
  title,
  follow = true,
  maxHeight = 420,
  emptyMessage,
  className,
}: LogConsoleProps) {
  const lines = Array.isArray(content) ? content : (content ?? "").split("\n");
  const isEmpty = lines.length === 0 || (lines.length === 1 && lines[0] === "");

  const t = useT();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(follow);
  const [copied, setCopied] = useState(false);

  // On ne recolle en bas que si l'utilisateur y était déjà : remonter dans un
  // journal pour lire une erreur, puis se faire renvoyer en bas à chaque
  // nouvelle ligne, est le comportement le plus irritant d'une console.
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 8;
    setPinned(atBottom);
  }, []);

  useEffect(() => {
    if (!follow || !pinned) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length, follow, pinned]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Presse-papiers indisponible (contexte non sécurisé) : rien à faire.
    }
  };

  const gutterWidth = `${String(lines.length).length + 1}ch`;

  return (
    <div className={cn("rounded border border-line overflow-hidden bg-console", className)}>
      <div className="flex items-center justify-between gap-3 px-3 h-8 bg-console-gutter border-b border-white/5">
        <span className="font-mono text-[11px] text-console-dim uppercase tracking-wider truncate">
          {title ?? t("common.console")}
          {!isEmpty && <span className="ml-2 normal-case tracking-normal">· {lines.length} {t("common.lines")}</span>}
        </span>
        {!isEmpty && (
          <button
            type="button"
            onClick={copy}
            className="inline-flex items-center gap-1 text-[11px] text-console-dim hover:text-console-ink transition-colors"
          >
            {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
            {copied ? t("common.copied") : t("common.copy")}
          </button>
        )}
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="overflow-auto font-mono text-[12px] leading-[1.55]"
        style={{ maxHeight }}
      >
        {isEmpty ? (
          <p className="px-3 py-4 text-console-dim">{emptyMessage ?? t("common.noOutput")}</p>
        ) : (
          <ol className="min-w-max py-1.5">
            {lines.map((line, index) => {
              const isError = ERROR_PATTERN.test(line);
              const isWarn = !isError && WARN_PATTERN.test(line);
              return (
                <li
                  key={index}
                  className={cn(
                    "flex border-l-2",
                    isError ? "border-failure bg-failure/10" : isWarn ? "border-unstable bg-unstable/10" : "border-transparent"
                  )}
                >
                  <span
                    className="select-none text-right pr-3 pl-2 text-console-dim tabular-nums flex-shrink-0"
                    style={{ width: gutterWidth }}
                    aria-hidden="true"
                  >
                    {index + 1}
                  </span>
                  <span className={cn("pr-4 whitespace-pre", isError ? "text-failure" : isWarn ? "text-unstable" : "text-console-ink")}>
                    {line || " "}
                  </span>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
