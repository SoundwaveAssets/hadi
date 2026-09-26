"use client";

import { useI18n, type Lang } from "@/lib/i18n";
import { cn } from "@/lib/cn";

const LANGS: Lang[] = ["fr", "en"];

export function LanguageToggle({ className }: { className?: string }) {
  const { lang, setLang, t } = useI18n();
  return (
    <div role="group" aria-label={t("lang.switch")} className={cn("inline-flex items-center rounded border border-chrome-line overflow-hidden", className)}>
      {LANGS.map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          title={t(`lang.${code}`)}
          className={cn(
            "h-6 px-2 text-[11px] font-semibold uppercase tracking-wide transition-colors",
            lang === code ? "bg-chrome-2 text-chrome-ink" : "text-chrome-ink-2 hover:text-chrome-ink"
          )}
        >
          {code}
        </button>
      ))}
    </div>
  );
}
