# Phase 2: gaps in the FastAPI (`api/`)

Phase 1 did not change `api/`. Everything below was either worked around in the
frontend (marked **workaround**) or left out (marked **missing**). Timings are from
the synthetic large fixture (352 CPUs, 2 833 samples, ~1 M rows in the CPU
section) on the 4-vCPU dev container, without Redis.

| # | Gap | Effect in Phase 1 | Status |
|---|-----|-------------------|--------|
| 1 | `GET /files/{name}/headers/{header}` takes the header as a **path parameter**. Aliases or raw headers containing `/` (`I/O and transfer rate`, `rxpck/s …`) return 404 even URL-encoded, because Starlette decodes `%2F` before routing. | Device list unknown for these headers; the chart falls back to the API's default device. Today no multi-device alias contains `/`, so the visible result is the same, but raw (un-aliased) headers would lose their devices. | workaround |
| 2 | `GET /files/{name}/data` returns **one device per request** and has no "all devices" mode. | Overview of a multi-device header (Block Devices, IFACE, …) costs 1 + N requests, each re-reading and re-splitting the whole parquet. The frontend limits concurrency to 4. | workaround |
| 3 | `/data` is **slow on large files**: 1.7–13 s for `header=CPU` (the `all` aggregate, only 2 833 rows) on the 1 M-row file, typically 2–7 s (7 calls). `prepare_df_for_pandas` splits every line of the header before filtering the device; nothing is cached between requests. | The CPU card shows a skeleton for several seconds. Statistics cost the same again. | missing |
| 4 | `/data` JSON is **row-oriented** and carries float32 artefacts (`7.170000076293945`). | 729 KB for the 10-metric CPU chart (2 833 rows); 25.6 MB for 352 per-core series. The frontend converts rows to columns and rounds to 2 decimals. A columnar format (`{"date": [...], "%usr": [...]}`), rounding, Arrow IPC or an optional server-side `max_points` (LTTB) would cut size and parse time. | workaround |
| 5 | `GET /files/{name}` returns restarts as **raw text lines** (`"12:00:00  LINUX RESTART\t(4 CPU)\n 12:00:00"`), no timestamp field. | Frontend parses the last token as time of day. Note: the Bokeh path inserts zero rows at restarts (`insert_restarts_into_df`), `/data` does not; the ECharts charts draw a dashed marker line instead. | workaround |
| 6 | No list of **sample timestamps**. Streamlit offers start/end as dropdowns of the real timestamps (`translate_dates_into_list`). | Free `HH:MM:SS` time inputs limited to the file's min/max; the API filters with `>=`/`<=`. Works, but the user cannot see which timestamps exist. | workaround |
| 7 | No endpoint for the **`device_num`** ("all of N") of CPU-like headers. | Derived from the device list of `/headers/{header}` (one extra request per alias). | workaround |
| 8 | **Metric descriptions** (`metric` table, the "man pages" tab) are not exposed. | Not shown. | missing |
| 9 | **Duplicate timestamps** (`dup_bool` / `dup_check`, the "multiple indexes" warning) are not reported by `/data`. | No warning in the new UI. | missing |
| 10 | No **token revocation / logout**. Tokens are stateless HMAC tokens valid for `SAR_API_TOKEN_TTL` (24 h). | Logout deletes the httpOnly cookie only; a copied token stays valid until it expires. | workaround |
| 11 | No **combined overview data** endpoint (the JSON twin of `POST /charts/overview`). | The overview is assembled from 2–3 requests per alias. | workaround |
| 12 | No **combined statistics CSV** ("Generate csv for all statistical data"). `/statistics?format=csv` exists per header. | Not offered in Phase 1. | missing |
| 13 | `GET /files` has no metadata (host, sar date, OS, time range). | Host/date are parsed from the file name convention `<upload date>_<host>_<sar date>`. | workaround |
| 14 | No **upload progress for the server-side parse** (upload returns after parsing). | Progress bar covers the transfer; then "Parsing on the server…" without progress. | workaround |
| 15 | SSO (`/sso/token`, `/sso/validate`) is built for the Streamlit UI redirect (`SAR_UI_BASE_URL`). | Next.js only has the username/password login. | missing |

## Frontend-side notes (no API change needed)

- **No CORS change.** The browser only talks to Next.js; `/api/v1/*` is rewritten
  to the API and `proxy.ts` injects `Authorization: Bearer <token>` from the
  httpOnly cookie.
- **Uploads bypass the rewrite.** Next.js buffers request bodies on
  proxy-matched paths and silently cuts them at 10 MB
  (`experimental.proxyClientMaxBodySize`). Uploads therefore go through the
  streaming route handler `app/api/upload`; a direct `POST /api/v1/files` through
  Next.js is rejected with 405. Verified with the 120 MB large fixture
  (1 011 381 rows arrived).
- **PDF export** (`POST /charts/overview`, Bokeh + Selenium) exists in the API but
  is not wired into Phase 1 and was not tested.

## Suggested order for Phase 2

1. Columnar `/data` with rounding + `devices=all` + optional `max_points` (fixes 2, 3, 4, 11 in one go; biggest effect on large files).
2. Query-parameter variant of the header details (fixes 1) and `timestamps`/`device_count` in it (6, 7).
3. Structured restarts in `GET /files/{name}` (5) and `GET /metrics` (8).
4. Token revocation or short-lived tokens + refresh (10).
