"use client";

import { useEffect, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type StatisticsResponse } from "@/lib/api";
import { apiLimit } from "@/lib/limit";

type Props = { file: string; alias: string; device: string | null; start?: string; end?: string };

// pandas describe() rows, in its own order
const STATS = ["count", "mean", "std", "min", "25%", "50%", "75%", "max"];

function format(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function StatisticsTable({ file, alias, device, start, end }: Props) {
  const [stats, setStats] = useState<StatisticsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    apiLimit(() => api.statistics(file, { header: alias, device, start, end }, controller.signal))
      .then(setStats)
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [file, alias, device, start, end]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!stats) return <Skeleton className="h-48 w-full" />;

  const metrics = Object.keys(stats.statistics);
  return (
    <div className="max-h-[380px] overflow-auto" data-testid="statistics-table">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Metric</TableHead>
            {STATS.map((stat) => (
              <TableHead key={stat} className="text-right">
                {stat}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {metrics.map((metric) => (
            <TableRow key={metric}>
              <TableCell className="font-mono text-xs">{metric}</TableCell>
              {STATS.map((stat) => (
                <TableCell key={stat} className="text-right tabular-nums">
                  {format(stats.statistics[metric][stat])}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
