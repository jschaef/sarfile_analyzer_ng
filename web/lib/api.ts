// Browser-side client for the FastAPI. All calls are same-origin: /api/v1/*
// is rewritten to the API and proxy.ts attaches the bearer token.

export type SarFile = { name: string; size_bytes: number };

export type HeaderInfo = { header: string; alias: string; metrics: string[] };

export type FileInfo = {
  name: string;
  os_details: string;
  start: string;
  end: string;
  restarts: string[];
  headers: HeaderInfo[];
};

export type HeaderDetails = {
  header: string;
  alias: string;
  metrics: string[];
  devices: string[];
  start: string;
  end: string;
};

export type DataRow = { date: string } & Record<string, number | string | null>;

export type DataResponse = {
  header: string;
  alias: string;
  device: string | null;
  rows: number;
  data: DataRow[];
};

export type StatisticsResponse = {
  header: string;
  alias: string;
  device: string | null;
  statistics: Record<string, Record<string, number | null>>;
};

export type UploadResult = {
  uploaded: { name: string; rows: number; headers: number; warnings: string[] }[];
  errors: { file: string; detail: string }[];
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function handleUnauthorized() {
  await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  // full reload on purpose: drops all client state of the expired session
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/login?next=${next}`);
}

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 401) {
    await handleUnauthorized();
    throw new ApiError("Session expired", 401);
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof body?.detail === "string" ? body.detail : `Request failed (${response.status})`;
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return fetch(`/api/v1${path}`, { signal, cache: "no-store" }).then((r) => parse<T>(r));
}

const enc = encodeURIComponent;

export const api = {
  me: () => get<{ username: string; role: string }>("/users/me"),
  listFiles: () => get<{ files: SarFile[] }>("/files").then((r) => r.files),
  fileInfo: (name: string, signal?: AbortSignal) => get<FileInfo>(`/files/${enc(name)}`, signal),
  headerDetails: (name: string, header: string, signal?: AbortSignal) =>
    get<HeaderDetails>(`/files/${enc(name)}/headers/${enc(header)}`, signal),
  data: (
    name: string,
    params: { header: string; device?: string | null; start?: string; end?: string },
    signal?: AbortSignal,
  ) => get<DataResponse>(`/files/${enc(name)}/data?${query(params)}`, signal),
  statistics: (
    name: string,
    params: { header: string; device?: string | null; start?: string; end?: string },
    signal?: AbortSignal,
  ) => get<StatisticsResponse>(`/files/${enc(name)}/statistics?${query(params)}`, signal),
  deleteFile: (name: string) =>
    fetch(`/api/v1/files/${enc(name)}`, { method: "DELETE" }).then((r) =>
      parse<{ deleted: string }>(r),
    ),
  // XMLHttpRequest instead of fetch: fetch has no upload progress events,
  // and SAR files are often >100 MB.
  upload: (files: File[], onProgress?: (fraction: number) => void) =>
    new Promise<UploadResult>((resolve, reject) => {
      const form = new FormData();
      for (const file of files) form.append("files", file, file.name);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
      xhr.responseType = "json";
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress?.(event.loaded / event.total);
      };
      xhr.onerror = () => reject(new ApiError("Upload failed - network error", 0));
      xhr.onload = () => {
        const body = xhr.response;
        if (xhr.status === 401) {
          void handleUnauthorized();
          reject(new ApiError("Session expired", 401));
        } else if (body && Array.isArray(body.errors)) {
          // a batch where every file failed comes back as 400 with the same shape
          resolve(body as UploadResult);
        } else {
          reject(new ApiError(body?.detail ?? `Upload failed (${xhr.status})`, xhr.status));
        }
      };
      xhr.send(form);
    }),
};

function query(params: Record<string, string | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value);
  }
  return search.toString();
}
