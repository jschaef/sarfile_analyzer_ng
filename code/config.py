#!/usr/bin/python3
import json
import logging
import os

logger = logging.getLogger(__name__)

# Settings an admin can change at runtime (web frontend: Admin > Settings).
# They are stored in $UPLOAD_DIR/config/settings.json, next to the other shared
# state, and take precedence over the environment variables below; removing an
# entry falls back to the environment (or the default) again. Every process -
# Streamlit, API, sar-web-api - sees a change on its next read, because the
# file's modification time is checked on every access.
#
# name -> (type, environment variable, minimum, maximum); min/max bound the
# value of an int and the length of a str
EDITABLE_SETTINGS = {
    "admin_email": (str, "ADMIN_EMAIL", 3, 200),
    "admin_communication": (str, "ADMIN_COMMUNICATION", 0, 200),
    "max_header_count": (int, "MAX_HEADER_COUNT", 1, 12),
    "cols_per_line": (int, "COLS_PER_LINE", 1, 8),
    "redis_enabled": (bool, "REDIS_ENABLED", None, None),
    "redis_host": (str, "REDIS_HOST", 1, 255),
    "redis_port": (int, "REDIS_PORT", 1, 65535),
    "redis_user": (str, "REDIS_USER", 0, 100),
    "redis_password": (str, "REDIS_PASSWORD", 0, 500),
    # the new web frontend (sarfile_analyzer_web); Streamlit links to it in
    # the sidebar, empty = no link
    "web_frontend_url": (str, "WEB_FRONTEND_URL", 0, 300),
    # and back: the web frontend links to this Streamlit app in its header
    "streamlit_url": (str, "STREAMLIT_URL", 0, 300),
}
URL_SETTINGS = {"web_frontend_url", "streamlit_url"}
SECRET_SETTINGS = {"redis_password"}

_cache = {}  # settings path -> ((mtime_ns, size), values)


def settings_path(upload_dir=None):
    upload_dir = upload_dir or type.__getattribute__(Config, "upload_dir")
    return os.path.join(upload_dir, "config", "settings.json")


def stored_settings(upload_dir=None) -> dict:
    """The values set by an admin; {} when there are none."""
    path = settings_path(upload_dir)
    try:
        stat = os.stat(path)
    except OSError:
        return {}
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _cache.get(path)
    if cached and cached[0] == key:
        return cached[1]
    try:
        with open(path) as handle:
            loaded = json.load(handle)
        values = {k: v for k, v in loaded.items() if k in EDITABLE_SETTINGS}
    except (OSError, ValueError, AttributeError):
        logger.warning("ignoring unreadable settings file %s", path)
        values = {}
    _cache[path] = (key, values)
    return values


def validate_setting(name: str, value):
    """The value converted to the setting's type; ValueError if it is invalid."""
    if name not in EDITABLE_SETTINGS:
        raise ValueError(f"unknown setting {name!r}")
    kind, _, low, high = EDITABLE_SETTINGS[name]
    if kind is bool:
        if not isinstance(value, bool):
            raise ValueError(f"{name}: true or false expected")
        return value
    if kind is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name}: a whole number is expected")
        if not low <= value <= high:
            raise ValueError(f"{name}: must be between {low} and {high}")
        return value
    if not isinstance(value, str):
        raise ValueError(f"{name}: text expected")
    value = value.strip()
    if not low <= len(value) <= high:
        raise ValueError(f"{name}: {low} to {high} characters")
    if name == "admin_email" and "@" not in value:
        raise ValueError("admin_email: not an e-mail address")
    if name == "redis_host" and any(c.isspace() for c in value):
        raise ValueError("redis_host: no spaces allowed")
    if name in URL_SETTINGS and value:
        if not value.startswith(("https://", "http://")) or any(c.isspace() for c in value):
            raise ValueError(f"{name}: an http(s) URL is expected")
    return value


def update_settings(changes: dict, upload_dir=None) -> dict:
    """Store admin settings; a value of None removes the setting.

    All changes are validated before anything is written. The file is
    replaced atomically and readable by the owner only (it may hold the
    Redis password).
    """
    values = dict(stored_settings(upload_dir))
    for name, value in changes.items():
        if value is None:
            if name not in EDITABLE_SETTINGS:
                raise ValueError(f"unknown setting {name!r}")
            values.pop(name, None)
        else:
            values[name] = validate_setting(name, value)
    path = settings_path(upload_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(values, handle, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return values


def environment_value(name: str):
    """The value from the environment or the default, ignoring admin settings."""
    return type.__getattribute__(Config, name)


class _ConfigMeta(type):
    """Config.<setting> returns the admin's value when one is stored."""

    def __getattribute__(cls, name):
        value = type.__getattribute__(cls, name)
        if name in EDITABLE_SETTINGS:
            stored = stored_settings()
            if name in stored:
                return stored[name]
        return value


class Config(object, metaclass=_ConfigMeta):
    upload_dir = os.getenv("UPLOAD_DIR", "upload")
    redis_enabled = os.getenv("REDIS_ENABLED", "True").lower() in ("true", "1", "t")
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_user = os.getenv("REDIS_USER", "")
    redis_password = os.getenv("REDIS_PASSWORD", "")
    rkey_pref = os.getenv("RKEY_PREF", "user")
    pdf_name = os.getenv("PDF_NAME", "sar_chart.pdf")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example-org.com")
    max_metric_header = int(os.getenv("MAX_METRIC_HEADER", 8))
    cols_per_line = int(os.getenv("COLS_PER_LINE", 4))
    max_header_count = int(os.getenv("MAX_HEADER_COUNT", 6))
    file_type = os.getenv("FILE_TYPE", "parquet")
    admin_communication = os.getenv("ADMIN_COMMUNICATION", "slack")
    web_frontend_url = os.getenv("WEB_FRONTEND_URL", "")
    streamlit_url = os.getenv("STREAMLIT_URL", "")
    debug = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")
    use_streamlit_bokeh_component = os.getenv("USE_STREAMLIT_BOKEH_COMPONENT", "True").lower() in (
        "true",
        "1",
        "t",
    )
