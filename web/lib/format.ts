export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

// Upload names follow '<upload date>_<host>_<sar date>' (helpers_pl.rename_sar_file).
export function describeFileName(name: string): { host: string; sarDate: string; uploaded: string } | null {
  const match = /^(\d{4}-\d{2}-\d{2})_(.+)_(\d{4}-\d{2}-\d{2})$/.exec(name);
  if (!match) return null;
  return { uploaded: match[1], host: match[2], sarDate: match[3] };
}
