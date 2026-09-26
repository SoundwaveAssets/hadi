"use client";

import { cn } from "@/lib/cn";
import { useI18n } from "@/lib/i18n";

export interface DayActivity {
  date: string;
  total: number;
  deployed?: number;
  blocked?: number;
}

const CELL = 11;
const GAP = 3;
const PITCH = CELL + GAP;
const WEEKS = 53;
const LABEL_LEFT = 30;
const LABEL_TOP = 18;

const LABELED_DAYS = [1, 3, 5];
const LEVEL_OPACITY = [0, 0.3, 0.52, 0.76, 1];

function toKey(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function level(count: number, max: number): number {
  if (count <= 0) return 0;
  if (max <= 1) return 4;
  const ratio = count / max;
  if (ratio <= 0.25) return 1;
  if (ratio <= 0.5) return 2;
  if (ratio <= 0.75) return 3;
  return 4;
}

interface ActivityHeatmapProps {
  data: DayActivity[];
  className?: string;
}

export function ActivityHeatmap({ data, className }: ActivityHeatmapProps) {
  const { t, lang } = useI18n();
  const locale = lang === "en" ? "en-GB" : "fr-FR";
  const shortMonth = (m: number) => new Date(Date.UTC(2024, m, 1)).toLocaleDateString(locale, { month: "short", timeZone: "UTC" });
  const shortDay = (d: number) => new Date(Date.UTC(2024, 0, 7 + d)).toLocaleDateString(locale, { weekday: "short", timeZone: "UTC" });
  const longDate = (d: Date) => d.toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  const byDay = new Map(data.map((d) => [d.date, d]));

  // Fenêtre : de « il y a 52 semaines, dimanche » à aujourd'hui.
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  const start = new Date(today);
  start.setUTCDate(today.getUTCDate() - (WEEKS - 1) * 7 - today.getUTCDay());

  const max = Math.max(0, ...data.map((d) => d.total));
  let total = 0;

  const cells: { x: number; y: number; key: string; count: number; deployed: number; blocked: number; date: Date }[] = [];
  const monthMarks: { x: number; label: string }[] = [];
  let lastMonth = -1;

  for (let week = 0; week < WEEKS; week++) {
    for (let dow = 0; dow < 7; dow++) {
      const date = new Date(start);
      date.setUTCDate(start.getUTCDate() + week * 7 + dow);
      if (date > today) continue;

      const key = toKey(date);
      const entry = byDay.get(key);
      const count = entry?.total ?? 0;
      total += count;

      cells.push({
        x: LABEL_LEFT + week * PITCH,
        y: LABEL_TOP + dow * PITCH,
        key,
        count,
        deployed: entry?.deployed ?? 0,
        blocked: entry?.blocked ?? 0,
        date,
      });

      if (dow === 0 && date.getUTCMonth() !== lastMonth && week < WEEKS - 2) {
        lastMonth = date.getUTCMonth();
        monthMarks.push({ x: LABEL_LEFT + week * PITCH, label: shortMonth(lastMonth) });
      }
    }
  }
  if (monthMarks.length > 1 && monthMarks[1].x - monthMarks[0].x < PITCH * 3) monthMarks.shift();

  const width = LABEL_LEFT + WEEKS * PITCH;
  const height = LABEL_TOP + 7 * PITCH;

  return (
    <div className={cn("space-y-2", className)}>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          className="block max-w-full h-auto"
          role="img"
          aria-label={t("heatmap.total", { n: total })}
        >
          {monthMarks.map((m) => (
            <text key={m.x} x={m.x} y={11} fontSize={10} fill="var(--color-ink-3)" fontFamily="var(--font-sans)">
              {m.label}
            </text>
          ))}

          {LABELED_DAYS.map((dow) => (
            <text key={dow} x={0} y={LABEL_TOP + dow * PITCH + CELL - 2} fontSize={10} fill="var(--color-ink-3)" fontFamily="var(--font-sans)">
              {shortDay(dow)}
            </text>
          ))}

          {cells.map((c) => {
            const lvl = level(c.count, max);
            const label = longDate(c.date);
            const detail = c.count === 0 ? t("heatmap.none", { date: label }) : t("heatmap.day", { n: c.count, date: label });
            return (
              <rect
                key={c.key}
                x={c.x}
                y={c.y}
                width={CELL}
                height={CELL}
                rx={2}
                fill={lvl === 0 ? "var(--color-line)" : "var(--color-accent)"}
                fillOpacity={lvl === 0 ? 1 : LEVEL_OPACITY[lvl]}
                data-level={lvl}
              >
                <title>{detail}</title>
              </rect>
            );
          })}
        </svg>
      </div>

      <div className="flex items-center justify-between gap-4 text-[12px] text-ink-2">
        <span>{t("heatmap.total", { n: total })}</span>
        <span className="flex items-center gap-1.5 text-ink-3">
          {t("heatmap.legend.less")}
          {LEVEL_OPACITY.map((opacity, i) => (
            <span
              key={i}
              className="inline-block w-[11px] h-[11px] rounded-[2px]"
              style={{
                background: i === 0 ? "var(--color-line)" : "var(--color-accent)",
                opacity: i === 0 ? 1 : opacity,
              }}
              aria-hidden="true"
            />
          ))}
          {t("heatmap.legend.more")}
        </span>
      </div>
    </div>
  );
}
