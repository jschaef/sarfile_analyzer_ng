"use client";

import { BarChart3Icon, FileUpIcon, RefreshCwIcon, Trash2Icon, UploadIcon } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type SarFile } from "@/lib/api";
import { describeFileName, formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";

export function FileManager() {
  const [files, setFiles] = useState<SarFile[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setFiles(await api.listFiles());
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Could not load files");
    }
  }, []);

  useEffect(() => {
    // initial load; state updates happen after the request resolves
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  async function upload(selected: File[]) {
    if (selected.length === 0) return;
    setProgress(0);
    try {
      const result = await api.upload(selected, setProgress);
      for (const item of result.uploaded) {
        toast.success(`Uploaded as ${item.name}`, {
          description: `${item.rows.toLocaleString()} rows, ${item.headers} headers`,
        });
        for (const warning of item.warnings) toast.warning(warning);
      }
      for (const error of result.errors) toast.error(`${error.file}: ${error.detail}`);
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setProgress(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function remove(name: string) {
    setDeleting(name);
    try {
      await api.deleteFile(name);
      toast.success(`${name} deleted`);
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Delete failed");
    } finally {
      setDeleting(null);
      setConfirming(null);
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void upload(Array.from(event.dataTransfer.files));
  }

  const uploading = progress !== null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Manage SAR Files</h1>
        <p className="text-sm text-muted-foreground">
          Upload sar text files (<code>sar -A</code>), binary <code>saXX</code> files, sadf JSON or
          .xz archives. Files are renamed to <code>&lt;upload date&gt;_&lt;host&gt;_&lt;sar date&gt;</code>.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Upload</CardTitle>
          <CardDescription>Drop files here or choose them. Several files at once are fine.</CardDescription>
        </CardHeader>
        <CardContent>
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
              "flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 text-center transition-colors",
              dragging ? "border-primary bg-primary/5" : "border-border",
            )}
          >
            <FileUpIcon className="size-8 text-muted-foreground" />
            <input
              ref={inputRef}
              type="file"
              multiple
              className="sr-only"
              id="sar-upload"
              data-testid="upload-input"
              onChange={(event) => void upload(Array.from(event.target.files ?? []))}
              disabled={uploading}
            />
            <Button onClick={() => inputRef.current?.click()} disabled={uploading}>
              <UploadIcon /> Choose files
            </Button>
            {uploading && (
              <div className="w-full max-w-md space-y-1" data-testid="upload-progress">
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full bg-primary transition-[width]"
                    style={{ width: `${Math.round((progress ?? 0) * 100)}%` }}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  {progress !== null && progress < 1
                    ? `Uploading… ${Math.round(progress * 100)}%`
                    : "Parsing on the server…"}
                </p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="space-y-1.5">
            <CardTitle>Your files</CardTitle>
            <CardDescription>{files ? `${files.length} file(s)` : "Loading…"}</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refresh()}>
            <RefreshCwIcon /> Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {loadError && <p className="text-sm text-destructive">{loadError}</p>}
          {!files && !loadError && (
            <div className="space-y-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          )}
          {files && files.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">No files uploaded yet.</p>
          )}
          {files && files.length > 0 && (
            <Table data-testid="file-table">
              <TableHeader>
                <TableRow>
                  <TableHead>File</TableHead>
                  <TableHead>Host</TableHead>
                  <TableHead>SAR date</TableHead>
                  <TableHead className="text-right">Size</TableHead>
                  <TableHead className="w-0 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {files.map((file) => {
                  const parts = describeFileName(file.name);
                  return (
                    <TableRow key={file.name} data-testid="file-row" data-file={file.name}>
                      <TableCell className="font-mono text-xs">{file.name}</TableCell>
                      <TableCell>{parts?.host ?? "–"}</TableCell>
                      <TableCell>{parts?.sarDate ?? "–"}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatBytes(file.size_bytes)}</TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-2">
                          <Link
                            href={`/overview?file=${encodeURIComponent(file.name)}`}
                            className={buttonVariants({ variant: "outline", size: "sm" })}
                          >
                            <BarChart3Icon /> Overview
                          </Link>
                          {confirming === file.name ? (
                            <>
                              <Button
                                variant="destructive"
                                size="sm"
                                onClick={() => void remove(file.name)}
                                disabled={deleting === file.name}
                                data-testid="confirm-delete"
                              >
                                {deleting === file.name ? "Deleting…" : "Confirm"}
                              </Button>
                              <Button variant="ghost" size="sm" onClick={() => setConfirming(null)}>
                                Cancel
                              </Button>
                            </>
                          ) : (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setConfirming(file.name)}
                              aria-label={`Delete ${file.name}`}
                              data-testid="delete-file"
                            >
                              <Trash2Icon />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
          {files && files.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              <Badge variant="secondary">Tip</Badge> Name format: upload date, host, date of the sar data.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
