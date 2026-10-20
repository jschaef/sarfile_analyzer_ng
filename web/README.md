# SAR Analyzer – Next.js frontend (Phase 1)

A web frontend for the existing FastAPI in [`../api`](../api). All parsing and
polars work stays in Python; this app only renders. Phase 1 covers:

- **Login**: username/password against the analyzer user DB; the API token is
  kept in an httpOnly cookie and never reaches browser JavaScript.
- **Manage SAR Files**: list, upload (drag & drop, several files, progress), delete.
- **Graphical Overview**: the overview page of the Streamlit app with header/alias
  selection (defaults: CPU, Kernel tables, Load, Memory utilization, Swap
  utilization), per-chart metric selection, time filter, Apache ECharts line
  charts with zoom, restart markers and a statistics tab.

Stack: Next.js 16.4.2 (App Router, Turbopack, Cache Components), React 19.3,
TypeScript strict, Tailwind CSS 4, shadcn/ui (Base UI), Apache ECharts 6.1,
next-themes (light/dark/system), Playwright.

## Architecture

```
browser ──► Next.js :3000 ──┬─ /api/auth/login|logout   route handlers, set/clear the httpOnly cookie
                            ├─ /api/upload              route handler, streams multipart to POST /api/v1/files
                            └─ /api/v1/*  ─ proxy.ts adds "Authorization: Bearer <cookie>"
                                          ─ rewrite (next.config.ts) ──► FastAPI :8100 /api/v1/*
```

- Same origin for the browser, so `api/` needs no CORS change.
- `proxy.ts` (Next 16's new name for middleware) also redirects pages to
  `/login` when no session cookie exists. The API validates the token on every
  call; a 401 drops the cookie and sends the user to the login page.
- Uploads do not go through the rewrite: Next.js buffers bodies on
  proxy-matched paths and cuts them at 10 MB.

### Overview rules taken over from `code/dia_overview_pl.py`

- Options are the file's aliases sorted ascending; the **diagram order follows
  that option order, not the click order** (`sel_order_map`).
- Headers without sub-devices → one chart. CPU-like headers (`^CPU|SOFT.*`) →
  only the `all` aggregate, labelled "all of N". Other multi-device headers
  (DEV, IFACE, …) → one chart per device, sorted by name.
- Charts: canvas renderer, LTTB sampling, `dataZoom` (wheel + slider), animation
  off, legend/metric menu to hide metrics, restarts as dashed red line, PNG export
  from the toolbox. ECharts' `large` mode does not exist for line series (only
  scatter/bar/lines), so it is not used. Option builder: `lib/echarts-option.ts`.

## Run locally

```bash
# 1. API (repo root, own venv)
python3 -m venv .venv && . .venv/bin/activate
pip install -r api/requirements.txt -r code/requirements.txt
export SAR_API_SECRET=$(openssl rand -hex 32) UPLOAD_DIR=/tmp/sar-upload REDIS_ENABLED=false
uvicorn api.main:app --host 127.0.0.1 --port 8100

# 2. frontend
cd web
npm ci
npm run dev                       # http://localhost:3000, seed login admin / password
```

Production: `npm run build && npm run start`.

| Variable | Default | Purpose |
|---|---|---|
| `SAR_API_URL` | `http://127.0.0.1:8100` | FastAPI base URL. Read by the rewrite **at build time** and by the route handlers at runtime – set it for both. |
| `SAR_COOKIE_SECURE` | `true` in production, else `false` | `Secure` flag of the session cookie. Set `false` only for plain-HTTP setups. |

The session cookie lives as long as the API token (`SAR_API_TOKEN_TTL`, 24 h).

## Checks

```bash
npm run lint
npm run typecheck
npm run build
npm run test:e2e        # needs a build; starts/reuses API (:8100) and Next.js (:3000)
```

E2E (`e2e/overview.spec.ts`): login → upload the small fixture → Overview with
the five default aliases → charts rendered → order/device rules → metric menu →
time filter → statistics → delete → logout (+ 401 afterwards), plus wrong
password and httpOnly cookie checks.

Options for the e2e run:

- `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/chrome` – use a preinstalled Chromium.
- `SAR_E2E_SKIP_API=1` – never start the API from Playwright; `SAR_E2E_API_CMD`
  changes the start command (default `uvicorn api.main:app --port 8100`, run in
  the repo root; needs `SAR_API_SECRET`/`UPLOAD_DIR` in the environment).
- `SAR_E2E_REAL_FILE=/path/to/sar-file SAR_E2E_REAL_HOST=<host>` – additionally
  runs `e2e/real-file.spec.ts` against a real sar file outside the repo.
- `SAR_SCREENSHOTS_DIR=docs/screenshots [SAR_SCREENSHOTS_WIDTH=1024]` – writes the
  login/overview screenshots in light and dark.

## Test data

There are no real sar files in the repo. `scripts/generate_sar.py` writes a
synthetic `sar -A` text report that `code/parse_into_polars.py` accepts
(deterministic, stdlib only):

```bash
# small fixture, checked in as e2e/fixtures/sar_small.txt (4 CPUs, 96 samples, 1 restart)
python3 scripts/generate_sar.py --cpus 4 --samples 96 --interval 900 --restart -o e2e/fixtures/sar_small.txt
# large fixture for the benchmark (352 CPUs, ~1 M rows in the CPU section, 120 MB) – not checked in
python3 scripts/generate_sar.py --cpus 352 --samples 2833 --interval 30 --minimal -o /tmp/sar_large.txt
```

## Performance

See [PERF.md](PERF.md) (ECharts vs BokehJS, `perf/`). API gaps for Phase 2:
[PHASE2-API-GAPS.md](PHASE2-API-GAPS.md).

## Layout

```
app/login                 login page + form
app/(app)/files           file management
app/(app)/overview        Graphical Overview (overview, alias-section, chart-card, statistics-table)
app/api/auth/*, api/upload  route handlers (cookie, streaming upload)
components/charts         ECharts wrapper (tree-shaken echarts/core)
components/ui             shadcn/ui components
lib/                      API client, sar data helpers, ECharts option builder
proxy.ts                  auth header injection + page guard
e2e/                      Playwright tests + small fixture
perf/                     benchmark (export_payloads.py, bench.mjs)
scripts/generate_sar.py   synthetic sar generator
```
