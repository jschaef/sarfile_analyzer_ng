"use client";

import { useEffect, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api";
import { apiLimit } from "@/lib/limit";
import { CPU_LIKE } from "@/lib/sar";
import { ChartCard } from "./chart-card";

type Props = {
  file: string;
  alias: string;
  start?: string;
  end?: string;
  restarts: number[];
};

type Plan = { charts: { device: string | null; subtitle?: string }[] };

// One header (alias) of the overview. Mirrors dia_compute.prepare_df_for_pandas:
// no sub-devices -> one chart; CPU-like -> only the 'all' aggregate ("all of N");
// other multi-device headers (DEV, IFACE, ...) -> one chart per device.
export function AliasSection({ file, alias, start, end, restarts }: Props) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    apiLimit(() => api.headerDetails(file, alias, controller.signal))
      .then((details) => {
        const devices = details.devices;
        if (devices.length === 0) {
          setPlan({ charts: [{ device: null }] });
        } else if (CPU_LIKE.test(alias)) {
          const count = devices.filter((d) => d !== "all").length;
          setPlan({ charts: [{ device: "all", subtitle: `all of ${count}` }] });
        } else {
          // str(sub_title) ordering, as in the Streamlit sort key
          const sorted = [...devices].sort();
          setPlan({ charts: sorted.map((device) => ({ device })) });
        }
      })
      .catch((e: Error) => {
        if (e.name === "AbortError") return;
        if (e instanceof ApiError && e.status === 404) {
          // The path parameter cannot carry aliases with '/' (e.g. "I/O and
          // transfer rate"): fall back to the API's default device. See
          // PHASE2-API-GAPS.md.
          setPlan({ charts: [{ device: null }] });
          return;
        }
        setError(e.message);
      });
    return () => controller.abort();
  }, [file, alias]);

  return (
    <section className="space-y-3" data-testid="alias-section" data-alias={alias}>
      <h2 className="text-lg font-semibold">{alias}</h2>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {!plan && !error && <Skeleton className="h-[440px] w-full" />}
      {plan?.charts.map((chart) => (
        <ChartCard
          key={chart.device ?? "-"}
          file={file}
          alias={alias}
          device={chart.device}
          subtitle={chart.subtitle ?? (plan.charts.length > 1 ? chart.device ?? undefined : undefined)}
          start={start}
          end={end}
          restarts={restarts}
        />
      ))}
    </section>
  );
}
