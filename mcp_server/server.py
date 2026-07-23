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
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image

API_URL = os.getenv("SAR_API_URL", "http://127.0.0.1:8100").rstrip("/")
API_PREFIX = "/api/v1"
OUTPUT_DIR = Path(
    os.getenv("SAR_MCP_OUTPUT_DIR", Path(__file__).resolve().parent / "output")
)
MAX_INLINE_IMAGE_BYTES = int(os.getenv("SAR_MCP_MAX_INLINE_IMAGE", 800_000))

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

_token: str | None = None
_token_expiry: float = 0.0


def _login(client: httpx.Client) -> str:
    global _token, _token_expiry
    username = os.getenv("SAR_API_USERNAME")
    password = os.getenv("SAR_API_PASSWORD")
    if not username or not password:
        raise RuntimeError("SAR_API_USERNAME / SAR_API_PASSWORD not configured")
    response = client.post(
        f"{API_URL}{API_PREFIX}/token",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    data = response.json()
    _token = data["access_token"]
    _token_expiry = data.get("expires_at", time.time() + 3600)
    return _token


def _request(
    method: str, path: str, *, expect_json: bool = True, **kwargs
) -> Any | httpx.Response:
    """Authenticated API call with automatic (re-)login."""
    with httpx.Client(timeout=300.0) as client:
        if _token is None or time.time() > _token_expiry - 60:
            _login(client)
        headers = {"Authorization": f"Bearer {_token}"}
        response = client.request(
            method, f"{API_URL}{API_PREFIX}{path}", headers=headers, **kwargs
        )
        if response.status_code == 401:
            headers = {"Authorization": f"Bearer {_login(client)}"}
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
def create_user(username: str, password: str, role: str = "user") -> dict:
    """Create a new analyzer user (web UI + API login).

    Requires the MCP server's configured API account to have the admin role.
    Roles: 'user' or 'admin'.
    """
    return _request(
        "POST", "/users", json={"username": username, "password": password, "role": role}
    )


@mcp.tool()
def list_users() -> dict:
    """List all analyzer users and their roles (admin only)."""
    return _request("GET", "/users")


@mcp.tool()
def list_sar_files() -> dict:
    """List the SAR files (parquet) available for analysis."""
    return _request("GET", "/files")


@mcp.tool()
def upload_sar_file(
    file_path: str | None = None,
    content_base64: str | None = None,
    filename: str | None = None,
) -> dict:
    """Upload a SAR file (ASCII or binary 'saXXXXXXXX') and convert it to
    parquet.

    Provide either file_path (a path readable by this MCP server) or
    content_base64 together with filename.
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
    return _request("POST", "/files", files={"files": (name, content)})


@mcp.tool()
def delete_sar_file(name: str) -> dict:
    """Delete an uploaded SAR file (parquet) from the server."""
    return _request("DELETE", f"/files/{name}")


@mcp.tool()
def get_file_info(name: str) -> dict:
    """OS details, time range, restarts and all headers (with aliases and
    metrics) of a SAR file."""
    return _request("GET", f"/files/{name}")


@mcp.tool()
def get_header_details(name: str, header: str) -> dict:
    """Metrics, sub-devices (CPUs, disks, NICs, ...) and time range for one
    header of a SAR file. `header` accepts an alias like 'CPU' or 'Load'."""
    return _request("GET", f"/files/{name}/headers/{header}")


@mcp.tool()
def get_statistics(
    name: str,
    header: str,
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
    return _request("GET", f"/files/{name}/statistics", params=params)


@mcp.tool()
def get_data(
    name: str,
    header: str,
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
    data = _request("GET", f"/files/{name}/data", params=params)
    if data["rows"] > max_rows:
        data["data"] = data["data"][:max_rows]
        data["truncated_to"] = max_rows
    return data


@mcp.tool()
def generate_chart(
    file: str,
    header: str,
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
    response = _request("POST", "/charts/single", json=body, expect_json=False)
    return _chart_result(response, f"{file}_{header}.{format}")


@mcp.tool()
def generate_overview(
    file: str,
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
    response = _request("POST", "/charts/overview", json=body, expect_json=False)
    suffix = "pdf" if format == "pdf" else "zip"
    return _chart_result(response, f"{file}_overview.{suffix}")


@mcp.tool()
def compare_files(
    files: list[str],
    header: str,
    metric: str,
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
    response = _request("POST", "/charts/multi", json=body, expect_json=False)
    return _chart_result(response, f"multi_{header}_{metric}.{format}")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
