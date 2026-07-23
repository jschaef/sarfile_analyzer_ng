"""MCP server (Streamable HTTP) for the SAR File Analyzer API.

Environment:
    SAR_API_URL        Base URL of the REST API (default http://127.0.0.1:8100)
    SAR_API_USERNAME   API user (existing analyzer account)
    SAR_API_PASSWORD   API password
    SAR_MCP_HOST       Bind address (default 127.0.0.1)
    SAR_MCP_PORT       Port (default 8200)
    SAR_MCP_OUTPUT_DIR Where generated PNG/PDF files are written
                       (default: <repo>/mcp_server/output)

Run:
    python -m mcp_server.server

The server is stateful (FastMCP default) - required for Streamable HTTP
clients behind reverse proxies. When proxying, force HTTP/1.1 and map
POST /mcp -> /mcp/ without an external redirect.
"""

import base64
import os
import time
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.utilities.types import Image

API_URL = os.getenv("SAR_API_URL", "http://127.0.0.1:8100").rstrip("/")
API_PREFIX = "/api/v1"
OUTPUT_DIR = Path(
    os.getenv("SAR_MCP_OUTPUT_DIR", Path(__file__).resolve().parent / "output")
)
MAX_INLINE_IMAGE_BYTES = int(os.getenv("SAR_MCP_MAX_INLINE_IMAGE", 800_000))

_verify_setting: object | None = None


def _ssl_verify() -> object:
    """TLS verification for the httpx client talking to the API.

    Default: httpx default (certifi + SSL_CERT_FILE if set), i.e. Python's
    strict RFC-5280 checks. Set SAR_MCP_TLS_RELAX_STRICT=1 to keep CA pinning
    but clear VERIFY_X509_STRICT — needed when the CA chain is not
    strict-clean (e.g. a private Sub-CA whose basicConstraints are not marked
    critical, which Python >=3.13 rejects). Trust is unchanged; only the RFC
    format nitpick is relaxed (same leniency curl/Node have by default).
    """
    global _verify_setting
    if _verify_setting is None:
        if os.getenv("SAR_MCP_TLS_RELAX_STRICT", "").lower() in ("1", "true", "yes"):
            import ssl

            ctx = ssl.create_default_context(cafile=os.getenv("SSL_CERT_FILE"))
            ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
            _verify_setting = ctx
        else:
            _verify_setting = True
    return _verify_setting

mcp = FastMCP(
    "sar-analyzer",
    host=os.getenv("SAR_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("SAR_MCP_PORT", "8200")),
    instructions=(
        "Analyze Linux sysstat/sar files: upload SAR files (converted to "
        "parquet automatically), list headers/metrics, fetch statistics and "
        "render charts as PNG or PDF. Charts are saved to the output "
        "directory; small PNGs are also returned inline."
    ),
)

# Per-MCP-session credentials: sessions start on the service account from the
# environment; the `login` tool switches a single session to another analyzer
# user without affecting other connected clients. Key 0 = env default.
_DEFAULT_KEY = 0
_sessions: dict[int, dict] = {}


def _default_creds() -> dict:
    return {
        "username": os.getenv("SAR_API_USERNAME"),
        "password": os.getenv("SAR_API_PASSWORD"),
        "token": None,
        "expiry": 0.0,
    }


def _session_key(ctx: Context | None) -> int:
    session = getattr(ctx, "session", None) if ctx else None
    return id(session) if session is not None else _DEFAULT_KEY


def _creds(session_key: int) -> dict:
    if session_key not in _sessions:
        _sessions[session_key] = _default_creds()
    return _sessions[session_key]


def _login_creds(client: httpx.Client, creds: dict) -> str:
    if not creds["username"] or not creds["password"]:
        raise RuntimeError(
            "No credentials: configure SAR_API_USERNAME/PASSWORD "
            "or use the login tool"
        )
    response = client.post(
        f"{API_URL}{API_PREFIX}/token",
        json={"username": creds["username"], "password": creds["password"]},
    )
    if response.status_code == 401:
        raise RuntimeError(f"Login failed for {creds['username']!r}: invalid credentials")
    response.raise_for_status()
    data = response.json()
    creds["token"] = data["access_token"]
    creds["expiry"] = data.get("expires_at", time.time() + 3600)
    return creds["token"]


def _request(
    method: str,
    path: str,
    *,
    session_key: int = _DEFAULT_KEY,
    expect_json: bool = True,
    **kwargs,
) -> Any | httpx.Response:
    """Authenticated API call with automatic (re-)login for the session's user."""
    creds = _creds(session_key)
    with httpx.Client(timeout=300.0, verify=_ssl_verify()) as client:
        if not creds["token"] or time.time() > creds["expiry"] - 60:
            _login_creds(client, creds)
        headers = {"Authorization": f"Bearer {creds['token']}"}
        response = client.request(
            method, f"{API_URL}{API_PREFIX}{path}", headers=headers, **kwargs
        )
        if response.status_code == 401:
            headers = {"Authorization": f"Bearer {_login_creds(client, creds)}"}
            response = client.request(
                method, f"{API_URL}{API_PREFIX}{path}", headers=headers, **kwargs
            )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise RuntimeError(f"API error {response.status_code}: {detail}")
        return response.json() if expect_json else response


def _save_output(payload: bytes, filename: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / filename
    target.write_bytes(payload)
    return target


def _filename_from_response(response: httpx.Response, fallback: str) -> str:
    disposition = response.headers.get("content-disposition", "")
    if 'filename="' in disposition:
        return disposition.split('filename="')[1].rstrip('"')
    return fallback


def _chart_result(response: httpx.Response, fallback_name: str) -> list:
    """Save the chart and return [description, Image?]."""
    payload = response.content
    filename = _filename_from_response(response, fallback_name)
    target = _save_output(payload, filename)
    result: list = [f"Saved: {target} ({len(payload)} bytes)"]
    if (
        response.headers.get("content-type", "").startswith("image/png")
        and len(payload) <= MAX_INLINE_IMAGE_BYTES
    ):
        result.append(Image(data=payload, format="png"))
    return result


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------
@mcp.tool()
def login(username: str, password: str, ctx: Context) -> dict:
    """Log this MCP session in as a different analyzer user.

    Only affects the current session: uploads, files and charts then belong
    to that user (upload/<username>/). Other connected clients keep their
    own login. Without login, the session uses the configured service
    account."""
    creds = {"username": username, "password": password, "token": None, "expiry": 0.0}
    with httpx.Client(timeout=60.0, verify=_ssl_verify()) as client:
        _login_creds(client, creds)
    _sessions[_session_key(ctx)] = creds
    me = _request("GET", "/users/me", session_key=_session_key(ctx))
    return {"logged_in_as": me["username"], "role": me["role"]}


@mcp.tool()
def logout(ctx: Context) -> dict:
    """Reset this MCP session back to the configured service account."""
    _sessions.pop(_session_key(ctx), None)
    default_user = os.getenv("SAR_API_USERNAME")
    return {"logged_in_as": default_user, "note": "back to service account"}


@mcp.tool()
def whoami(ctx: Context) -> dict:
    """Show which analyzer user this MCP session currently acts as."""
    return _request("GET", "/users/me", session_key=_session_key(ctx))


@mcp.tool()
def create_user(username: str, password: str, ctx: Context, role: str = "user") -> dict:
    """Create a new analyzer user (web UI + API login).

    The session's current user needs the admin role. Roles: 'user' or 'admin'.
    """
    return _request(
        "POST",
        "/users",
        session_key=_session_key(ctx),
        json={"username": username, "password": password, "role": role},
    )


@mcp.tool()
def list_users(ctx: Context) -> dict:
    """List all analyzer users and their roles (admin only)."""
    return _request("GET", "/users", session_key=_session_key(ctx))


@mcp.tool()
def list_sar_files(ctx: Context) -> dict:
    """List the SAR files (parquet) available for analysis."""
    return _request("GET", "/files", session_key=_session_key(ctx))


@mcp.tool()
def upload_sar_file(
    ctx: Context,
    file_path: str | None = None,
    content_base64: str | None = None,
    filename: str | None = None,
) -> dict:
    """Upload a SAR file (ASCII or binary 'saXXXXXXXX') and convert it to
    parquet.

    Prefer file_path: it is read where THIS MCP server runs and streamed to
    the API without base64. When the server runs locally (stdio), a normal
    local path just works. Only use content_base64 (+ filename) as a
    fallback when the file is not reachable from the server's filesystem;
    avoid it for large files (it inflates the request by ~33% and is passed
    inline).
    """
    if file_path:
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise RuntimeError(f"File not found: {path}")
        content = path.read_bytes()
        name = filename or path.name
    elif content_base64 and filename:
        content = base64.b64decode(content_base64)
        name = filename
    else:
        raise RuntimeError("Provide file_path or (content_base64 and filename)")
    return _request(
        "POST", "/files", session_key=_session_key(ctx), files={"files": (name, content)}
    )


@mcp.tool()
def delete_sar_file(name: str, ctx: Context) -> dict:
    """Delete an uploaded SAR file (parquet) from the server."""
    return _request("DELETE", f"/files/{name}", session_key=_session_key(ctx))


@mcp.tool()
def get_file_info(name: str, ctx: Context) -> dict:
    """OS details, time range, restarts and all headers (with aliases and
    metrics) of a SAR file."""
    return _request("GET", f"/files/{name}", session_key=_session_key(ctx))


@mcp.tool()
def get_header_details(name: str, header: str, ctx: Context) -> dict:
    """Metrics, sub-devices (CPUs, disks, NICs, ...) and time range for one
    header of a SAR file. `header` accepts an alias like 'CPU' or 'Load'."""
    return _request(
        "GET", f"/files/{name}/headers/{header}", session_key=_session_key(ctx)
    )


@mcp.tool()
def get_statistics(
    name: str,
    header: str,
    ctx: Context,
    metric: str | None = None,
    device: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """describe() statistics (count/mean/std/min/max/quartiles) for a header
    or a single metric. start/end accept 'HH:MM[:SS]' or ISO timestamps."""
    params = {
        k: v
        for k, v in {
            "header": header,
            "metric": metric,
            "device": device,
            "start": start,
            "end": end,
        }.items()
        if v is not None
    }
    return _request(
        "GET", f"/files/{name}/statistics", session_key=_session_key(ctx), params=params
    )


@mcp.tool()
def get_data(
    name: str,
    header: str,
    ctx: Context,
    metric: str | None = None,
    device: str | None = None,
    start: str | None = None,
    end: str | None = None,
    max_rows: int = 200,
) -> dict:
    """Raw time-series data for a header/metric as records. Large results are
    truncated to max_rows (increase deliberately if needed)."""
    params = {
        k: v
        for k, v in {
            "header": header,
            "metric": metric,
            "device": device,
            "start": start,
            "end": end,
        }.items()
        if v is not None
    }
    data = _request(
        "GET", f"/files/{name}/data", session_key=_session_key(ctx), params=params
    )
    if data["rows"] > max_rows:
        data["data"] = data["data"][:max_rows]
        data["truncated_to"] = max_rows
    return data


@mcp.tool()
def generate_chart(
    file: str,
    header: str,
    ctx: Context,
    metric: str | None = None,
    device: str | None = None,
    start: str | None = None,
    end: str | None = None,
    backend: str = "bokeh",
    format: str = "png",
    width: int = 1200,
    height: int = 400,
    font_size: int = 12,
) -> list:
    """Render a chart for one SAR file as PNG or PDF.

    With `metric` a single-metric detail chart, without it an overview of all
    metrics of the header. backend: 'bokeh' (like the web UI, needs Firefox
    on the API host) or 'altair' (browserless). The file is saved to the
    output directory; small PNGs are also returned inline.
    """
    body = {
        "file": file,
        "header": header,
        "metric": metric,
        "device": device,
        "start": start,
        "end": end,
        "backend": backend,
        "format": format,
        "width": width,
        "height": height,
        "font_size": font_size,
    }
    response = _request(
        "POST",
        "/charts/single",
        session_key=_session_key(ctx),
        json=body,
        expect_json=False,
    )
    return _chart_result(response, f"{file}_{header}.{format}")


@mcp.tool()
def generate_overview(
    file: str,
    ctx: Context,
    aliases: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    backend: str = "bokeh",
    format: str = "pdf",
    width: int = 1200,
    height: int = 400,
) -> list:
    """Graphical overview across several headers of one SAR file.

    Default headers: CPU, Kernel tables, Load, Memory utilization, Swap
    utilization. format 'pdf' = one multi-page PDF, 'png' = zip of PNGs.
    """
    body = {
        "file": file,
        "aliases": aliases,
        "start": start,
        "end": end,
        "backend": backend,
        "format": format,
        "width": width,
        "height": height,
    }
    response = _request(
        "POST",
        "/charts/overview",
        session_key=_session_key(ctx),
        json=body,
        expect_json=False,
    )
    suffix = "pdf" if format == "pdf" else "zip"
    return _chart_result(response, f"{file}_overview.{suffix}")


@mcp.tool()
def compare_files(
    files: list[str],
    header: str,
    metric: str,
    ctx: Context,
    device: str | None = None,
    mode: str = "overlay",
    backend: str = "bokeh",
    format: str = "png",
    width: int = 1200,
    height: int = 400,
) -> list:
    """Compare one metric across several SAR files (different days/hosts).

    mode 'overlay' stacks all days onto one 24h axis (one color per day),
    'sequential' keeps the real time axis.
    """
    body = {
        "files": files,
        "header": header,
        "metric": metric,
        "device": device,
        "mode": mode,
        "backend": backend,
        "format": format,
        "width": width,
        "height": height,
    }
    response = _request(
        "POST",
        "/charts/multi",
        session_key=_session_key(ctx),
        json=body,
        expect_json=False,
    )
    return _chart_result(response, f"multi_{header}_{metric}.{format}")


if __name__ == "__main__":
    # streamable-http (default): remote server on the host, zero client
    #   install, but client-local file uploads must go base64-through-context.
    # stdio: run this same server LOCALLY (per user, in the gemini/claude
    #   config), pointed at the remote SAR_API_URL. Then upload_sar_file with
    #   a LOCAL file_path streams the bytes straight to the API (no base64).
    transport = os.getenv("SAR_MCP_TRANSPORT", "streamable-http")
    mcp.run(transport=transport)
