# SAR File Analyzer — MCP Server

FastMCP server that lets AI agents drive the analyzer via the REST API
(`api/`): upload SAR files, inspect headers/metrics, fetch statistics, render
charts as PNG/PDF, and manage users. The server is only a thin HTTP client of
the REST API, so it can run either centrally (Streamable HTTP) or locally per
user (stdio) — the choice decides how file uploads work (see below).

## Two ways to run

`upload_sar_file(file_path=...)` reads the path **where the MCP server runs**.
That makes the transport choice matter:

| Mode | Install | `file_path` uploads | Best for |
|---|---|---|---|
| **Streamable HTTP** (central) | nothing on the client | only files already on the server host; a client-local file must go via `content_base64` (inflates the request, avoid for large files) | analysis/sharing of files already on the server |
| **stdio** (local, per user) | run this server locally | a **local** path streams straight to the API — no base64, no bloat | uploading your own SAR files from your machine |

Both talk to the same REST API and the same shared data.

### A) Streamable HTTP (central server)

```bash
pip install -r mcp_server/requirements.txt

SAR_API_URL=http://127.0.0.1:8100 \
SAR_API_USERNAME=<analyzer-user> SAR_API_PASSWORD=<password> \
SAR_MCP_HOST=0.0.0.0 SAR_MCP_PORT=8200 \
python -m mcp_server.server
```

MCP endpoint: `http://<host>:8200/mcp` (stateful). Client config:

```json
{ "mcpServers": { "sar-analyzer": { "type": "http", "url": "http://<host>:8200/mcp" } } }
```

### B) stdio (local, uploads your own files seamlessly)

Run the same server locally, pointed at the remote API. No server process to
keep alive — the client (gemini/Claude) starts it on demand. Then
`upload_sar_file` with a normal local path just works.

gemini-cli (`~/.gemini/settings.json`) / Claude Code (`~/.claude.json`):

```json
{
  "mcpServers": {
    "sar-analyzer": {
      "command": "/path/to/sarfile_analyzer_ng/code/venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/sarfile_analyzer_ng",
      "env": {
        "SAR_MCP_TRANSPORT": "stdio",
        "SAR_API_URL": "https://dus-lab-sar.lab.dus.suse.com:8443",
        "SAR_API_USERNAME": "<your-analyzer-user>",
        "SAR_API_PASSWORD": "<your-password>",
        "SSL_CERT_FILE": "/path/to/premium-support-dus-ca.pem",
        "SAR_MCP_OUTPUT_DIR": "/path/to/where/charts/should/land"
      }
    }
  }
}
```

Notes for stdio against the remote API:
- `SAR_API_URL` is the API port `:8443` (not the MCP `:9443`), and no MCP gate
  token is needed — you speak to the API directly.
- `SSL_CERT_FILE` gives Python the internal CA. If the cert lacks the AKI
  extension, Python's strict TLS may reject it — see the cert notes in
  `deployment/lab/README-lab.md`.
- Credentials can also be omitted here and set at runtime with the `login`
  tool.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `SAR_API_URL` | `http://127.0.0.1:8100` | REST API base URL |
| `SAR_API_USERNAME` / `SAR_API_PASSWORD` | — | analyzer account the server acts as (admin role needed for `create_user`/`list_users`) |
| `SAR_MCP_TRANSPORT` | `streamable-http` | `stdio` for the local per-user mode |
| `SAR_MCP_HOST` / `SAR_MCP_PORT` | `127.0.0.1` / `8200` | bind address (HTTP mode only) |
| `SAR_MCP_OUTPUT_DIR` | `mcp_server/output` | where generated PNG/PDF files are written |
| `SAR_MCP_MAX_INLINE_IMAGE` | `800000` | max PNG size (bytes) returned inline as MCP image |

## Tools

- `login(username, password)` / `logout()` / `whoami()` — switch THIS MCP
  session to another analyzer user (per-session; other clients keep their
  login; without login the session acts as the configured service account)
- `upload_sar_file(file_path | content_base64+filename)` — ASCII or binary SAR file, auto-converted to parquet
- `list_sar_files()` / `delete_sar_file(name)`
- `get_file_info(name)` — OS details, time range, restarts, headers
- `get_header_details(name, header)` — metrics, devices, time range
- `get_statistics(name, header, metric?, device?, start?, end?)`
- `get_data(...)` — raw time series (truncated to `max_rows`)
- `generate_chart(file, header, metric?, device?, ..., backend, format)` — PNG/PDF, saved to the output dir; small PNGs also returned inline
- `generate_overview(file, aliases?, format)` — multi-page PDF or PNG zip
- `compare_files(files, header, metric, mode=overlay|sequential, ...)`
- `create_user(username, password, role)` / `list_users()` — admin only

## Reverse-proxy notes (Caddy/nginx + VPN)

Lessons learned from the memory-search lab deployment apply here as well:

- The server is **stateful** (FastMCP default) — do not force stateless mode,
  otherwise the standalone GET SSE stream dies and follow-up POSTs 502.
- Map `POST /mcp` (no slash) internally to `/mcp/` instead of letting the
  proxy emit a 307 redirect (behind TLS the Location header downgrades).
- Force **HTTP/1.1** towards Node-based clients (gemini-cli, TS SDK) — h2
  hangs once the standalone GET SSE stream is open.
- If no server-initiated events are used, answering `GET /mcp*` with 405 at
  the proxy avoids idle-stream timeouts through VPN/NAT.
