"""FastAPI app for the SAR File Analyzer.

Run from the repo root:
    uvicorn api.main:app --host 0.0.0.0 --port 8100
"""

import hmac
import io
import logging
import os
import secrets
from urllib.parse import quote, urlencode

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import bootstrap  # noqa: F401
from . import auth, charts, services
from .services import ServiceError

logging.basicConfig(level=logging.INFO)

import sqlite2_polars


def _refresh_table_cache() -> None:
    """Rebuild the cached headings/metrics tables from SQLite on startup.

    The parquet copies under upload/config are shared with the web UI, so the
    API picks up database changes made while it was down.
    """
    try:
        sqlite2_polars.refresh_all_tables()
    except Exception as exc:  # a fresh/empty DB must not block startup
        logging.getLogger("sar_api").warning("table cache refresh failed: %s", exc)

app = FastAPI(
    title="SAR File Analyzer API",
    version="1.0.0",
    description=(
        "Programmatic access to the SAR file analyzer: upload SAR files "
        "(auto-converted to parquet), inspect headers/metrics, and render "
        "charts as PNG/PDF with the same engines as the web UI."
    ),
)

PREFIX = "/api/v1"


@app.on_event("startup")
def _on_startup() -> None:
    _refresh_table_cache()


@app.exception_handler(ServiceError)
async def service_error_handler(_, exc: ServiceError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------
class TokenRequest(BaseModel):
    username: str
    password: str


@app.post(f"{PREFIX}/token")
def issue_token(request: TokenRequest):
    if not auth.verify_credentials(request.username, request.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return auth.create_token(request.username)


# --------------------------------------------------------------------------
# SSO for the support platform (server-to-server, shared secret)
# --------------------------------------------------------------------------
SSO_SECRET = os.getenv("SAR_SSO_SECRET", "")
SSO_DEFAULT_PASSWORD = os.getenv("SAR_SSO_DEFAULT_PASSWORD", "")
UI_BASE_URL = os.getenv(
    "SAR_UI_BASE_URL", "https://dus-lab-sar.lab.dus.suse.com"
).rstrip("/")


class SsoTokenRequest(BaseModel):
    username: str = Field(
        min_length=2,
        pattern=services.USERNAME_PATTERN,
        description="Platform user (plain login or e-mail); provisioned on first use",
    )
    file: str | None = Field(
        default=None, description="Optional SAR file to preselect after the redirect"
    )


@app.post(f"{PREFIX}/sso/token")
def sso_token(
    request: SsoTokenRequest,
    x_sso_secret: str = Header(default="", alias="X-SSO-Secret"),
):
    """Exchange a shared secret for an API token plus a UI redirect URL.

    Called server-to-server by the support platform after it authenticated the
    user itself. Unknown users are provisioned just-in-time with role 'user'.
    """
    import sql_stuff

    if not SSO_SECRET:
        raise HTTPException(status_code=503, detail="SSO is not configured")
    if not hmac.compare_digest(x_sso_secret, SSO_SECRET):
        raise HTTPException(status_code=401, detail="Invalid SSO secret")

    created = False
    if request.username not in sql_stuff.view_all_users(kind="list"):
        password = SSO_DEFAULT_PASSWORD or secrets.token_urlsafe(24)
        if not sql_stuff.add_userdata(request.username, password, "user"):
            raise HTTPException(
                status_code=500, detail=f"Could not provision user {request.username!r}"
            )
        created = True
        services.user_dir(request.username)

    api_token = auth.create_token(request.username, purpose="api")
    ui_token = auth.create_token(request.username, purpose="ui")
    params = {"sso_token": ui_token["access_token"]}
    if request.file:
        params["file"] = request.file
    return {
        "username": request.username,
        "provisioned": created,
        "api_token": api_token,
        "ui_redirect_url": f"{UI_BASE_URL}/?{urlencode(params, quote_via=quote)}",
        "ui_token_expires_at": ui_token["expires_at"],
    }


@app.get(f"{PREFIX}/sso/validate")
def sso_validate(username: str = Depends(auth.consume_ui_token)):
    """Validate (and consume) an SSO UI token. Used by the Streamlit app."""
    import sql_stuff

    return {"username": username, "role": sql_stuff.get_role(username)}


# --------------------------------------------------------------------------
# user management (admin only)
# --------------------------------------------------------------------------
class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, pattern=services.USERNAME_PATTERN)
    password: str = Field(min_length=6)
    role: str = "user"


@app.get(f"{PREFIX}/users/me")
def get_me(username: str = Depends(auth.get_current_user)):
    import sql_stuff

    return {"username": username, "role": sql_stuff.get_role(username)}


@app.get(f"{PREFIX}/users")
def list_users(username: str = Depends(auth.get_current_user)):
    import sql_stuff

    auth.require_admin(username)
    return {
        "users": [
            {"username": name, "role": role} for name, role in sql_stuff.view_all_users()
        ]
    }


@app.post(f"{PREFIX}/users", status_code=201)
def create_user(
    request: CreateUserRequest, username: str = Depends(auth.get_current_user)
):
    import sql_stuff

    auth.require_admin(username)
    if request.role not in sql_stuff.ret_all_roles():
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role {request.role!r}; available: {sql_stuff.ret_all_roles()}",
        )
    if not sql_stuff.add_userdata(request.username, request.password, request.role):
        raise HTTPException(
            status_code=409, detail=f"User {request.username!r} already exists"
        )
    return {"created": request.username, "role": request.role}


# --------------------------------------------------------------------------
# file management
# --------------------------------------------------------------------------
@app.get(f"{PREFIX}/files")
def list_files(username: str = Depends(auth.get_current_user)):
    return {"files": services.list_sar_files(username)}


@app.post(f"{PREFIX}/files", status_code=201)
async def upload_files(
    files: list[UploadFile],
    username: str = Depends(auth.get_current_user),
):
    results, errors = [], []
    for upload in files:
        content = await upload.read()
        try:
            results.append(services.upload_sar_file(username, upload.filename, content))
        except ServiceError as exc:
            errors.append({"file": upload.filename, "detail": str(exc)})
    if not results and errors:
        return JSONResponse(status_code=400, content={"uploaded": [], "errors": errors})
    return {"uploaded": results, "errors": errors}


@app.delete(f"{PREFIX}/files/{{name}}")
def delete_file(name: str, username: str = Depends(auth.get_current_user)):
    services.delete_sar_file(username, name)
    return {"deleted": name}


@app.get(f"{PREFIX}/files/{{name}}")
def get_file_info(name: str, username: str = Depends(auth.get_current_user)):
    df = services.load_df(username, name)
    return {"name": name, **services.file_info(df)}


@app.get(f"{PREFIX}/files/{{name}}/headers/{{header}}")
def get_header_details(
    name: str, header: str, username: str = Depends(auth.get_current_user)
):
    return services.header_details(username, name, header)


# --------------------------------------------------------------------------
# data / statistics
# --------------------------------------------------------------------------
@app.get(f"{PREFIX}/files/{{name}}/data")
def get_data(
    name: str,
    header: str,
    metric: str | None = None,
    device: str | None = None,
    start: str | None = None,
    end: str | None = None,
    format: str = "json",
    username: str = Depends(auth.get_current_user),
):
    table, meta = services.get_table(username, name, header, metric, device, start, end)
    if format == "csv":
        buffer = io.StringIO()
        table.to_csv(buffer)
        return Response(content=buffer.getvalue(), media_type="text/csv")
    records = table.reset_index()
    records["date"] = records["date"].astype(str)
    return {
        "header": meta["header"],
        "alias": meta["alias"],
        "device": meta["device"],
        "rows": len(records),
        "data": records.to_dict(orient="records"),
    }


@app.get(f"{PREFIX}/files/{{name}}/statistics")
def get_statistics(
    name: str,
    header: str,
    metric: str | None = None,
    device: str | None = None,
    start: str | None = None,
    end: str | None = None,
    format: str = "json",
    username: str = Depends(auth.get_current_user),
):
    table, meta = services.get_table(username, name, header, metric, device, start, end)
    describe = table.describe()
    if format == "csv":
        buffer = io.StringIO()
        describe.to_csv(buffer)
        return Response(content=buffer.getvalue(), media_type="text/csv")
    return {
        "header": meta["header"],
        "alias": meta["alias"],
        "device": meta["device"],
        "statistics": {
            metric_name: {
                stat: (None if value != value else float(value))
                for stat, value in column.items()
            }
            for metric_name, column in describe.to_dict().items()
        },
    }


# --------------------------------------------------------------------------
# charts
# --------------------------------------------------------------------------
def _binary_response(payload: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_MEDIA = {"png": "image/png", "pdf": "application/pdf"}


class SingleChartRequest(BaseModel):
    file: str
    header: str = Field(description="Header alias (e.g. 'CPU') or raw header string")
    metric: str | None = Field(
        default=None, description="One metric for a detail chart; omit for all metrics"
    )
    device: str | None = None
    start: str | None = Field(default=None, description="'HH:MM[:SS]' or ISO timestamp")
    end: str | None = None
    backend: str = "bokeh"
    format: str = "png"
    width: int = 1200
    height: int = 400
    font_size: int = 12
    title: str | None = None


@app.post(f"{PREFIX}/charts/single")
def chart_single(
    request: SingleChartRequest, username: str = Depends(auth.get_current_user)
):
    payload, filename = charts.single_chart(
        username,
        request.file,
        request.header,
        metric=request.metric,
        device=request.device,
        start=request.start,
        end=request.end,
        backend=request.backend,
        fmt=request.format,
        width=request.width,
        height=request.height,
        font_size=request.font_size,
        title=request.title,
    )
    return _binary_response(payload, filename, _MEDIA[request.format])


class OverviewRequest(BaseModel):
    file: str
    aliases: list[str] | None = Field(
        default=None,
        description=f"Header aliases; default: {services.DEFAULT_OVERVIEW_ALIASES}",
    )
    start: str | None = None
    end: str | None = None
    backend: str = "bokeh"
    format: str = Field(default="pdf", description="'pdf' (multi-page) or 'png' (zip)")
    width: int = 1200
    height: int = 400
    font_size: int = 12


@app.post(f"{PREFIX}/charts/overview")
def chart_overview(
    request: OverviewRequest, username: str = Depends(auth.get_current_user)
):
    payload, filename, media_type = charts.overview(
        username,
        request.file,
        aliases=request.aliases,
        start=request.start,
        end=request.end,
        backend=request.backend,
        fmt=request.format,
        width=request.width,
        height=request.height,
        font_size=request.font_size,
    )
    return _binary_response(payload, filename, media_type)


class MultiChartRequest(BaseModel):
    files: list[str]
    header: str
    metric: str
    device: str | None = None
    mode: str = Field(
        default="overlay",
        description="'overlay' = days stacked on one 24h axis, "
        "'sequential' = real time axis",
    )
    backend: str = "bokeh"
    format: str = "png"
    width: int = 1200
    height: int = 400
    font_size: int = 12


@app.post(f"{PREFIX}/charts/multi")
def chart_multi(
    request: MultiChartRequest, username: str = Depends(auth.get_current_user)
):
    payload, filename = charts.multi_file_chart(
        username,
        request.files,
        request.header,
        request.metric,
        device=request.device,
        mode=request.mode,
        backend=request.backend,
        fmt=request.format,
        width=request.width,
        height=request.height,
        font_size=request.font_size,
    )
    return _binary_response(payload, filename, _MEDIA[request.format])


@app.get(f"{PREFIX}/health")
def health():
    return {"status": "ok"}
