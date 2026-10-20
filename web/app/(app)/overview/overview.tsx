"use client";

import { ArrowUpIcon, BarChart3Icon, ClockIcon, Undo2Icon, XIcon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type FileInfo, type SarFile } from "@/lib/api";
import { DEFAULT_OVERVIEW_ALIASES, restartTimes, timeOfDay } from "@/lib/sar";
import { cn } from "@/lib/utils";
import { AliasSection } from "./alias-section";

// Above this many diagrams the page gets heavy (dia_overview_pl warns too).
const MANY_ALIASES = 20;

type TimeRange = { start: string; end: string };

export function Overview() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fileParam = searchParams.get("file");

  const [files, setFiles] = useState<SarFile[] | null>(null);
  const [info, setInfo] = useState<FileInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listFiles()
      .then(setFiles)
      .catch((e: Error) => setError(e.message));
  }, []);

  const fileName = fileParam ?? files?.[0]?.name ?? null;

  useEffect(() => {
    if (!fileName) return;
    const controller = new AbortController();
    api
      .fileInfo(fileName, controller.signal)
      .then((result) => {
        setInfo(result);
        setError(null);
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [fileName]);

  function selectFile(name: string) {
    router.replace(`/overview?file=${encodeURIComponent(name)}`);
  }

  if (files && files.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>No SAR files yet</CardTitle>
          <CardDescription>Upload a file first, then come back to the overview.</CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/files" className={buttonVariants()}>
            Manage SAR Files
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Graphical Overview</h1>
          <p className="text-sm text-muted-foreground">Overview of important metrics from SAR data</p>
        </div>
        <div className="flex min-w-72 flex-col gap-1.5">
          <Label htmlFor="file-select">SAR file</Label>
          <select
            id="file-select"
            data-testid="file-select"
            className="h-8 rounded-lg border border-input bg-background px-2 text-sm dark:bg-input/30"
            value={fileName ?? ""}
            onChange={(event) => selectFile(event.target.value)}
            disabled={!files}
          >
            {files?.map((file) => (
              <option key={file.name} value={file.name}>
                {file.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Could not load the file</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!info || info.name !== fileName ? (
        !error && <Skeleton className="h-48 w-full" />
      ) : (
        // keyed by file: switching files starts from a clean selection
        <OverviewForFile key={info.name} info={info} />
      )}
    </div>
  );
}

function OverviewForFile({ info }: { info: FileInfo }) {
  // Ascending, like the pills in dia_overview_pl.metric_expander. This order
  // (not the click order) decides the order of the diagrams (sel_order_map).
  const options = useMemo(() => [...new Set(info.headers.map((h) => h.alias))].sort(), [info]);
  const [chosen, setChosen] = useState<Set<string>>(
    () => new Set(options.filter((alias) => DEFAULT_OVERVIEW_ALIASES.includes(alias))),
  );
  const selected = options.filter((alias) => chosen.has(alias));

  const fullRange: TimeRange = { start: timeOfDay(info.start), end: timeOfDay(info.end) };
  const [draft, setDraft] = useState<TimeRange>(fullRange);
  const [range, setRange] = useState<TimeRange>(fullRange);
  const [shown, setShown] = useState(false);

  const restarts = useMemo(() => restartTimes(info.restarts, info.start), [info]);
  const rangeError = draft.start > draft.end ? "Start must not be after end" : null;
  const isFullRange = range.start === fullRange.start && range.end === fullRange.end;

  function toggle(alias: string) {
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(alias)) next.delete(alias);
      else next.add(alias);
      return next;
    });
  }

  function show() {
    if (rangeError) return;
    setRange(draft);
    setShown(true);
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Select which metrics to display</CardTitle>
          <CardDescription className="break-all">{info.os_details}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => setChosen(new Set(options))}>
              Select all
            </Button>
            <Button variant="outline" size="sm" onClick={() => setChosen(new Set())}>
              Deselect all
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setChosen(new Set(options.filter((a) => DEFAULT_OVERVIEW_ALIASES.includes(a))))}
            >
              <Undo2Icon /> Defaults
            </Button>
          </div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="SAR metrics" data-testid="alias-pills">
            {options.map((alias) => {
              const active = chosen.has(alias);
              return (
                <button
                  key={alias}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggle(alias)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-sm transition-colors",
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-background hover:bg-muted",
                  )}
                >
                  {alias}
                </button>
              );
            })}
          </div>
          {selected.length > MANY_ALIASES && (
            <Alert>
              <AlertDescription>
                {selected.length} metrics selected. Large files with many diagrams take a while and need
                a lot of browser memory - consider a shorter time range.
              </AlertDescription>
            </Alert>
          )}

          <div className="flex flex-wrap items-end gap-4 border-t pt-4">
            <div className="space-y-1.5">
              <Label htmlFor="start-time">
                <ClockIcon className="size-3.5" /> Start time
              </Label>
              <Input
                id="start-time"
                type="time"
                step={1}
                min={fullRange.start}
                max={fullRange.end}
                value={draft.start}
                onChange={(event) => setDraft({ ...draft, start: event.target.value })}
                className="w-36"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="end-time">End time</Label>
              <Input
                id="end-time"
                type="time"
                step={1}
                min={fullRange.start}
                max={fullRange.end}
                value={draft.end}
                onChange={(event) => setDraft({ ...draft, end: event.target.value })}
                className="w-36"
              />
            </div>
            <Button variant="ghost" size="sm" onClick={() => setDraft(fullRange)}>
              Full day
            </Button>
            <div className="ml-auto flex gap-2">
              <Button onClick={show} disabled={selected.length === 0 || !!rangeError} data-testid="show-diagrams">
                <BarChart3Icon /> {shown ? "Update diagrams" : "Show diagrams"}
              </Button>
              {shown && (
                <Button variant="outline" onClick={() => setShown(false)}>
                  <XIcon /> Clear
                </Button>
              )}
            </div>
          </div>
          {rangeError && <p className="text-sm text-destructive">{rangeError}</p>}
          <p className="text-xs text-muted-foreground">
            Data from {info.start} to {info.end}
            {restarts.length > 0 && ` · ${restarts.length} restart(s), shown as dashed red line`}. Zoom with
            the mouse wheel or the slider below each chart; click a legend entry to hide a metric.
          </p>
        </CardContent>
      </Card>

      {shown && (
        <div className="space-y-8" id="diagrams" data-testid="diagrams">
          {!isFullRange && (
            <p className="text-sm text-muted-foreground">
              Time range {range.start} – {range.end}
            </p>
          )}
          {selected.map((alias) => (
            <AliasSection
              key={`${alias}|${range.start}|${range.end}`}
              file={info.name}
              alias={alias}
              start={isFullRange ? undefined : range.start}
              end={isFullRange ? undefined : range.end}
              restarts={restarts}
            />
          ))}
          <a href="#" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowUpIcon /> Back to top
          </a>
        </div>
      )}
    </>
  );
}
