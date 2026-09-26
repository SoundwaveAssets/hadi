"use client";

import { formatDistanceToNowStrict } from "date-fns";
import { enGB, fr } from "date-fns/locale";
import { useI18n, type Lang } from "@/lib/i18n";

const LOCALE: Record<Lang, string> = { fr: "fr-FR", en: "en-GB" };
const DATE_FNS_LOCALE = { fr, en: enGB } as const;

/** Formats de date qui suivent la langue de l'interface, pas celle du navigateur. */
export function useFormatDate() {
  const { lang } = useI18n();
  const locale = LOCALE[lang];
  return {
    /** 20/09/2026 14:05 */
    dateTime: (iso: string) => new Date(iso).toLocaleString(locale, { dateStyle: "short", timeStyle: "short" }),
    /** 20/09 14:05 */
    shortDateTime: (iso: string) => {
      const d = new Date(iso);
      return `${d.toLocaleDateString(locale, { day: "2-digit", month: "2-digit" })} ${d.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}`;
    },
    /** 20 septembre 2026 */
    longDate: (iso: string) => new Date(iso).toLocaleDateString(locale, { year: "numeric", month: "long", day: "numeric" }),
    /** il y a 3 minutes */
    relative: (iso: string) => formatDistanceToNowStrict(new Date(iso), { addSuffix: true, locale: DATE_FNS_LOCALE[lang] }),
    number: (n: number) => n.toLocaleString(locale),
  };
}
