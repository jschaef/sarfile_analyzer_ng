# SAR File Analyzer — REST API

FastAPI service that exposes the analyzer's functionality programmatically.
It reuses the modules in `code/` directly (polars parsing, sqlite metadata,
Bokeh/Altair chart builders) — no Streamlit session involved.

## Run

```bash
# dependencies (into the same venv as code/requirements.txt)
pip install -r api/requirements.txt

# from the repo root
SAR_API_SECRET=<random-hex> uvicorn api.main:app --host 0.0.0.0 --port 8100
```

Interactive docs: `http://<host>:8100/docs`

## Configuration (environment)

| Variable | Default | Purpose |
|---|---|---|
| `SAR_API_SECRET` | random per process | HMAC secret for bearer tokens; set it so tokens survive restarts |
| `SAR_API_TOKEN_TTL` | `86400` | token lifetime in seconds |
| `UPLOAD_DIR` | `code/upload` | same per-user storage as the web UI |
| `REDIS_ENABLED` etc. | see `code/config.py` | parquet cache, optional |

## Auth

`POST /api/v1/token` with `{"username": ..., "password": ...}` against the
existing analyzer user DB (`userstable`). All other endpoints expect
`Authorization: Bearer <token>`. Files live in `upload/<username>/`, exactly
like in the web UI.

## Endpoints (prefix `/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/token` | login, returns bearer token |
| POST | `/sso/token` | SSO for an external platform (see below) |
| GET | `/sso/validate` | consume an SSO UI token (used by the Streamlit app) |
| GET/POST | `/users` | list/create users (admin role required) |
| GET | `/files` | list SAR files of the user |
| POST | `/files` | multipart upload (multiple files, binary `saXXXXXXXX` auto-converted via `sar -A`, eager parquet conversion) |
| GET | `/files/{name}` | OS details, time range, restarts, headers+aliases+metrics |
| DELETE | `/files/{name}` | delete file + parquet + redis cache entry |
| GET | `/files/{name}/headers/{header}` | metrics, sub-devices, time range for one header (alias or raw header) |
| GET | `/files/{name}/data` | time series as JSON/CSV (`header`, optional `metric`, `device`, `start`, `end`, `format`) |
| GET | `/files/{name}/statistics` | describe() statistics as JSON/CSV |
| POST | `/charts/single` | one header: single-metric detail chart or all-metrics overview → PNG/PDF |
| POST | `/charts/overview` | several headers (default: CPU, Kernel tables, Load, Memory utilization, Swap utilization) → multi-page PDF or PNG zip |
| POST | `/charts/multi` | one metric across several files; `mode=overlay` (days on one 24h axis) or `sequential` → PNG/PDF |

Time bounds `start`/`end` accept `HH:MM[:SS]` (combined with the sar file's
date) or full ISO timestamps.

## SSO for an external platform

Lets another application (which authenticated a user itself) upload SAR files
in that user's context and then hand the user over to the analyzer web UI
already logged in. The classic UI login is unaffected.

**1. Platform backend exchanges the shared secret for tokens:**

```bash
curl -X POST https://<host>:8443/api/v1/sso/token \
  -H "X-SSO-Secret: $SAR_SSO_SECRET" -H 'Content-Type: application/json' \
  -d '{"username":"alice","file":"2026-07-24_host_2026-07-14"}'
```

```json
{
  "username": "alice",
  "provisioned": true,
  "api_token": {"access_token": "...", "expires_at": 1784964790},
  "ui_redirect_url": "https://<host>/?sso_token=...&file=...",
  "ui_token_expires_at": 1784878570
}
```

Unknown users are provisioned just-in-time with role `user` and
`SAR_SSO_DEFAULT_PASSWORD` (so they can also use the classic UI login later).

**2. Upload with `api_token`** — normal `POST /files`, files land in
`upload/alice/`.

**3. Redirect the browser to `ui_redirect_url`** — the UI validates the token
against `/sso/validate`, logs the user in, jumps to *Analyze Data* and
preselects `file` when given.

Security properties:

- `X-SSO-Secret` is server-to-server only; never expose it to a browser.
- Tokens carry a purpose: an `api` token is rejected by `/sso/validate`, a
  `ui` token is rejected by every data endpoint.
- The `ui` token is **single-use** (Redis-backed when available) and expires
  after `SAR_SSO_UI_TTL` seconds (default 180), because it travels in a URL.
  The UI also strips it from the address bar immediately.

Extra environment for this feature:

| Variable | Default | Purpose |
|---|---|---|
| `SAR_SSO_SECRET` | unset (feature disabled → 503) | shared secret for `/sso/token` |
| `SAR_SSO_DEFAULT_PASSWORD` | random per user | password for JIT-provisioned users |
| `SAR_SSO_UI_TTL` | `180` | lifetime of the UI redirect token in seconds |
| `SAR_UI_BASE_URL` | `https://dus-lab-sar.lab.dus.suse.com` | base of the redirect URL |

## Chart backends

- `backend=bokeh` (default): identical to the web UI. PNG/PDF export needs a
  Selenium browser on the API host — Firefox+geckodriver first (same as the
  UI's PDF export), automatic fallback to headless Chrome.
- `backend=altair`: rendered via vl-convert, no browser required.
