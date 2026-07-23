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

## Chart backends

- `backend=bokeh` (default): identical to the web UI. PNG/PDF export needs a
  Selenium browser on the API host — Firefox+geckodriver first (same as the
  UI's PDF export), automatic fallback to headless Chrome.
- `backend=altair`: rendered via vl-convert, no browser required.
