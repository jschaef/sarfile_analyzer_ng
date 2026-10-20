import type { DataRow } from "@/lib/api";

// Mirrors services.DEFAULT_OVERVIEW_ALIASES / dia_overview_pl.initial_aliases.
export const DEFAULT_OVERVIEW_ALIASES = [
  "CPU",
  "Kernel tables",
  "Load",
  "Memory utilization",
  "Swap utilization",
];

// Same rule as services._CPU_LIKE and dia_compute.prepare_df_for_pandas:
// CPU-like headers collapse to the 'all' aggregate in the overview.
export const CPU_LIKE = /^CPU|SOFT.*/i;

export type Columns = {
  x: number[]; // epoch milliseconds, sar wall-clock time interpreted as UTC
  series: Record<string, number[]>;
  metrics: string[];
};

// "2026-10-01 13:05:00" -> epoch ms. sar timestamps carry no time zone; they
// are treated as UTC and the charts render with useUTC so the axis shows the
// wall-clock time from the file, independent of the browser's zone.
export function parseSarDate(value: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(value);
  if (!match) return Number.NaN;
  const [, y, mo, d, h, mi, s] = match.map(Number);
  return Date.UTC(y, mo - 1, d, h, mi, s);
}

// Row-oriented API JSON -> column arrays (what ECharts' dataset wants).
export function toColumns(rows: DataRow[]): Columns {
  const metrics = rows.length > 0 ? Object.keys(rows[0]).filter((key) => key !== "date") : [];
  const x = new Array<number>(rows.length);
  const series: Record<string, number[]> = {};
  for (const metric of metrics) series[metric] = new Array<number>(rows.length);
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    x[i] = parseSarDate(row.date);
    for (const metric of metrics) {
      const value = row[metric];
      // null/NaN stay gaps; values arrive as float32 noise (7.170000076...)
      series[metric][i] = typeof value === "number" ? Math.round(value * 100) / 100 : Number.NaN;
    }
  }
  return { x, series, metrics };
}

// file_info().restarts holds the raw "LINUX RESTART" lines with the time
// appended as the last token, e.g. "12:00:00  LINUX RESTART\t(4 CPU)\n 12:00:00".
export function restartTimes(restarts: string[], fileStart: string): number[] {
  const day = fileStart.slice(0, 10);
  return restarts
    .map((line) => line.trim().split(/\s+/).at(-1) ?? "")
    .filter((time) => /^\d{2}:\d{2}:\d{2}$/.test(time))
    .map((time) => parseSarDate(`${day} ${time}`));
}

// "HH:MM:SS" part of an API timestamp, for <input type="time">.
export function timeOfDay(value: string): string {
  return value.slice(11, 19);
}
