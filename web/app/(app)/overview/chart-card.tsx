"use client";

import { ListFilterIcon } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { LineChart } from "@/components/charts/line-chart";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { apiLimit } from "@/lib/limit";
import { toColumns, type Columns } from "@/lib/sar";
import { StatisticsTable } from "./statistics-table";

type Props = {
  file: string;
  alias: string;
  device: string | null;
  subtitle?: string;
  start?: string;
  end?: string;
  restarts: number[];
};

const NO_RESTARTS: number[] = [];

export function ChartCard({ file, alias, device, subtitle, start, end, restarts }: Props) {
  const { resolvedTheme } = useTheme();
  const [columns, setColumns] = useState<Columns | null>(null);
  const [rowCount, setRowCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [tab, setTab] = useState<string>("chart");

  useEffect(() => {
    const controller = new AbortController();
    apiLimit(() => api.data(file, { header: alias, device, start, end }, controller.signal))
      .then((response) => {
        setColumns(toColumns(response.data));
        setRowCount(response.rows);
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [file, alias, device, start, end]);

  // restart markers only make sense inside the plotted range
  const visibleRestarts =
    columns && restarts.some((x) => x >= columns.x[0] && x <= columns.x[columns.x.length - 1])
      ? restarts
      : NO_RESTARTS;
  const metrics = columns?.metrics ?? [];
  const visibleCount = metrics.filter((m) => selected[m] !== false).length;
  // the section heading already names the alias; the card names the device
  const title = subtitle && device && device !== "all" ? `${alias} ${device}` : alias;

  function setAll(visible: boolean) {
    setSelected(Object.fromEntries(metrics.map((m) => [m, visible])));
  }

  return (
    <Card size="sm" data-testid="chart-card" data-alias={alias} data-device={device ?? ""}>
      <CardHeader>
        {title !== alias && <CardTitle>{device}</CardTitle>}
        <CardDescription>
          {subtitle && subtitle !== device && <span className="mr-2 font-medium">{subtitle}</span>}
          {columns && `${rowCount.toLocaleString()} samples · ${metrics.length} metrics`}
        </CardDescription>
        {columns && (
          <CardAction>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={<Button variant="outline" size="sm" data-testid="metric-filter" />}
              >
                <ListFilterIcon /> Metrics {visibleCount}/{metrics.length}
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="max-h-80 w-56">
                <DropdownMenuGroup>
                  <DropdownMenuLabel>Show metrics</DropdownMenuLabel>
                  <DropdownMenuItem onClick={() => setAll(true)}>Show all</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setAll(false)}>Hide all</DropdownMenuItem>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                {metrics.map((metric) => (
                  <DropdownMenuCheckboxItem
                    key={metric}
                    checked={selected[metric] !== false}
                    onCheckedChange={(checked) => setSelected((s) => ({ ...s, [metric]: checked }))}
                    closeOnClick={false}
                  >
                    {metric}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {!columns && !error && <Skeleton className="h-[380px] w-full" />}
        {columns && (
          <Tabs value={tab} onValueChange={(value) => setTab(String(value))}>
            <TabsList>
              <TabsTrigger value="chart">Chart</TabsTrigger>
              <TabsTrigger value="statistics">Statistics</TabsTrigger>
            </TabsList>
            <TabsContent value="chart" keepMounted>
              <LineChart
                columns={columns}
                restarts={visibleRestarts}
                dark={resolvedTheme === "dark"}
                selected={selected}
                onSelectedChange={setSelected}
                label={`${title} chart`}
              />
            </TabsContent>
            <TabsContent value="statistics">
              {tab === "statistics" && (
                <StatisticsTable file={file} alias={alias} device={device} start={start} end={end} />
              )}
            </TabsContent>
          </Tabs>
        )}
      </CardContent>
    </Card>
  );
}
