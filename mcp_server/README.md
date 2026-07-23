# SAR File Analyzer — MCP Server

FastMCP server (Streamable HTTP) that lets AI agents drive the analyzer via
the REST API (`api/`): upload SAR files, inspect headers/metrics, fetch
statistics, render charts as PNG/PDF, and manage users.

## Run

```bash
pip install -r mcp_server/requirements.txt

SAR_API_URL=http://127.0.0.1:8100 \
SAR_API_USERNAME=<analyzer-user> \
SAR_API_PASSWORD=<password> \
SAR_MCP_HOST=0.0.0.0 SAR_MCP_PORT=8200 \
python -m mcp_server.server
```

MCP endpoint: `http://<host>:8200/mcp` (Streamable HTTP, stateful).

Client config example (Claude Code):

```json
{ "mcpServers": { "sar-analyzer": { "type": "http", "url": "http://<host>:8200/mcp" } } }
```

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `SAR_API_URL` | `http://127.0.0.1:8100` | REST API base URL |
| `SAR_API_USERNAME` / `SAR_API_PASSWORD` | — | analyzer account the server acts as (admin role needed for `create_user`/`list_users`) |
| `SAR_MCP_HOST` / `SAR_MCP_PORT` | `127.0.0.1` / `8200` | bind address |
| `SAR_MCP_OUTPUT_DIR` | `mcp_server/output` | where generated PNG/PDF files are written |
| `SAR_MCP_MAX_INLINE_IMAGE` | `800000` | max PNG size (bytes) returned inline as MCP image |

## Tools

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
