"""Headless service layer: reuses the pure data functions from code/.

Everything here works without a Streamlit session. The functions mirror what
mng_sar.py / single_file_pl.py / dia_overview_pl.py / multi_files_pl.py do in
the UI, minus widgets and st.session_state.
"""

import logging
import os
import re
from pathlib import Path

import pandas as pd
import polars as pl

from . import bootstrap  # noqa: F401

import dia_compute_pl as dia_compute
import helpers_pl as helpers
import parse_into_polars as parse_polars
import pl_helpers2 as pl_h2
import redis_mng
import sar_ingest
from config import Config
from mng_sar import convert_openpgp_sar_file, is_sar_binary_file

logger = logging.getLogger("sar_api")

DEFAULT_OVERVIEW_ALIASES = [
    "CPU",
    "Kernel tables",
    "Load",
    "Memory utilization",
    "Swap utilization",
]

_CPU_LIKE = re.compile(r"^CPU|SOFT.*", re.IGNORECASE)
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


class ServiceError(Exception):
    """Raised for user-facing errors (bad file name, unknown header, ...)."""


class _LogCol:
    """Stand-in for the Streamlit column object rename_sar_file writes to."""

    def info(self, msg):
        logger.info(msg)

    def warning(self, msg):
        logger.warning(msg)


def user_dir(username: str) -> Path:
    directory = Path(Config.upload_dir) / username
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _validate_file_name(name: str) -> str:
    if not _SAFE_NAME.match(name) or name.startswith("."):
        raise ServiceError(f"Invalid file name: {name!r}")
    return name


def list_sar_files(username: str) -> list[dict]:
    directory = user_dir(username)
    entries = [x for x in os.listdir(directory) if (directory / x).is_file()]
    raw = [x for x in entries if not x.endswith(".parquet")]
    parquet = [x.removesuffix(".parquet") for x in entries if x.endswith(".parquet")]
    result = []
    for name in sorted(set(raw + parquet)):
        path = directory / name
        if not path.exists():
            path = directory / f"{name}.parquet"
        result.append({"name": name, "size_bytes": path.stat().st_size})
    return result


def upload_sar_file(username: str, filename: str, content: bytes) -> dict:
    """Store one SAR file (ASCII or binary) and convert it to parquet.

    Mirrors the 'Add Sar Files' flow in mng_sar.file_mng, then parses the
    file eagerly so the parquet exists when the request returns.
    """
    from magic import Magic

    directory = user_dir(username)
    warnings: list[str] = []

    # xz archives are unpacked, sadf JSON is converted to classic sar text
    try:
        content, filename, ingest_warnings = sar_ingest.preprocess_upload(
            content, filename
        )
    except ValueError as exc:
        raise ServiceError(str(exc))
    warnings.extend(ingest_warnings)

    detected = Magic().from_buffer(content)
    is_openpgp = "OpenPGP Secret Key" in detected
    is_generic_data = "data" in detected.lower()
    if is_openpgp or (is_generic_data and is_sar_binary_file(content, filename)):
        converted, new_name = convert_openpgp_sar_file(content, filename)
        if converted is None:
            raise ServiceError(
                f"Binary SAR file {filename} could not be converted; "
                "is the sysstat 'sar' binary installed and version-compatible?"
            )
        content, filename = converted, new_name
        detected = Magic().from_buffer(content)
        warnings.append(f"{filename}: binary SAR file converted with sar -A")

    if "ASCII text" not in detected:
        raise ServiceError(f"{filename}: unsupported file type ({detected})")

    temp_path = directory / f".tmp_{filename}"
    temp_path.write_bytes(content)
    renamed = helpers.rename_sar_file(str(temp_path), col=_LogCol())
    if not renamed:
        raise ServiceError(f"{filename}: could not extract host/date for renaming")

    if (directory / f"{renamed}.parquet").exists():
        warnings.append(f"{renamed}: existing parquet was overwritten")

    try:
        redis_mng.del_redis_key_property(
            f"{Config.rkey_pref}:{username}", f"{renamed}_parquet"
        )
    except Exception:
        pass

    # Eager conversion (the UI does this lazily on first analysis). Always
    # re-parse so a re-upload refreshes a stale parquet.
    df = parse_polars.parse_sar_file(str(directory / renamed), username, DEBUG=False)

    return {
        "name": renamed,
        "rows": df.height,
        "headers": len(pl_h2.get_headers(df)),
        "warnings": warnings,
    }


def delete_sar_file(username: str, name: str) -> None:
    name = _validate_file_name(name)
    directory = user_dir(username)
    removed = False
    for candidate in (directory / name, directory / f"{name}.parquet"):
        if candidate.exists():
            candidate.unlink()
            removed = True
    if not removed:
        raise ServiceError(f"File {name} not found")
    try:
        redis_mng.del_redis_key_property(
            f"{Config.rkey_pref}:{username}", f"{name}_parquet"
        )
    except Exception:
        pass


def load_df(username: str, name: str) -> pl.DataFrame:
    name = _validate_file_name(name)
    directory = user_dir(username)
    if not (directory / name).exists() and not (directory / f"{name}.parquet").exists():
        raise ServiceError(f"File {name} not found")
    return parse_polars.get_data_frame(str(directory / name), username)


def file_info(df: pl.DataFrame) -> dict:
    headers = pl_h2.get_headers(df)
    aliases = helpers.translate_headers(headers)
    os_details = pl_h2.get_os_details_from_df(df)
    restarts = pl_h2.get_restart_headers(df)
    dates = df["date"]
    return {
        "os_details": os_details.strip(),
        "start": str(dates.min()),
        "end": str(dates.max()),
        "restarts": [r.strip() for r in restarts],
        "headers": [
            {"header": h, "alias": a, "metrics": h.split()}
            for h, a in sorted(aliases.items(), key=lambda kv: kv[1])
        ],
    }


def resolve_header(df: pl.DataFrame, name: str) -> tuple[str, str]:
    """Accept an alias ('CPU', 'Load') or a raw header string.

    Returns (header, alias).
    """
    headers = pl_h2.get_headers(df)
    if name in headers:
        alias = helpers.translate_headers([name]).get(name, name)
        return name, alias
    translated = helpers.translate_aliases([name], headers)
    header = translated.get(name)
    if header and header in headers:
        return header, name
    raise ServiceError(f"Unknown header or alias: {name!r}")


def header_details(username: str, name: str, header_name: str) -> dict:
    df = load_df(username, name)
    header, alias = resolve_header(df, header_name)
    df_h = pl_h2.get_data_frames_from__headers([header], df, "header")[0]
    devices = dia_compute.get_device_list(df_h)
    return {
        "header": header,
        "alias": alias,
        "metrics": header.split(),
        "devices": devices,
        "start": str(df_h["date"].min()),
        "end": str(df_h["date"].max()),
    }


def _parse_bound(value: str | None, reference: pd.Timestamp) -> pd.Timestamp | None:
    """Parse 'HH:MM[:SS]' (combined with the sar file's date) or a full ISO
    timestamp."""
    if not value:
        return None
    value = value.strip()
    if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", value):
        parts = [int(x) for x in value.split(":")]
        while len(parts) < 3:
            parts.append(0)
        return reference.normalize() + pd.Timedelta(
            hours=parts[0], minutes=parts[1], seconds=parts[2]
        )
    try:
        return pd.Timestamp(value)
    except ValueError:
        raise ServiceError(f"Unparsable time value: {value!r}")


def filter_time_range(
    df: pd.DataFrame, start: str | None, end: str | None
) -> pd.DataFrame:
    if not start and not end:
        return df
    reference = df.index.min()
    start_ts = _parse_bound(start, reference)
    end_ts = _parse_bound(end, reference)
    if start_ts is not None:
        df = df[df.index >= start_ts]
    if end_ts is not None:
        df = df[df.index <= end_ts]
    if df.empty:
        raise ServiceError("Time range selection produced an empty data set")
    return df


def prepare_header_frames(
    df: pl.DataFrame, header: str, device: str | None = None
) -> list[dict]:
    """Polars header slice -> list of per-device pandas frames.

    Wraps dia_compute.prepare_df_for_pandas; `device` picks one sub-device
    (e.g. '3' or 'eth0'), otherwise the UI default is kept (CPU-like headers
    collapse to the 'all' aggregate).
    """
    df_h = pl_h2.get_data_frames_from__headers([header], df, "header")[0]
    start, end = df_h["date"].min(), df_h["date"].max()

    alias = helpers.translate_headers([header]).get(header, header)
    if device is not None and _CPU_LIKE.search(alias):
        # prepare_df_for_pandas only yields 'all' for CPU-like headers; build
        # the requested device frame directly (headless variant of
        # dia_compute.prepare_single_device_for_pandas).
        metrics_df = pl_h2.get_metrics_from_df(df_h, header, alias)
        device_df = pl_h2.get_df_from_sub_device(metrics_df, "sub_device", str(device))
        if device_df.height == 0:
            raise ServiceError(f"Device {device!r} not found for header {alias!r}")
        device_df = pl_h2.create_metrics_df(device_df, header)
        return [
            {
                "df": device_df.to_pandas().set_index("date"),
                "title": alias,
                "sub_title": str(device),
                "device_num": 1,
                "stats_pl": None,
            }
        ]

    frames = dia_compute.prepare_df_for_pandas(df_h, start, end)
    if device is not None:
        frames = [f for f in frames if str(f["sub_title"]) == str(device)]
        if not frames:
            raise ServiceError(f"Device {device!r} not found for header {alias!r}")
    return frames


def get_table(
    username: str,
    name: str,
    header_name: str,
    metric: str | None = None,
    device: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Time-filtered wide dataframe for one header (optionally one metric)."""
    df = load_df(username, name)
    header, alias = resolve_header(df, header_name)
    frames = prepare_header_frames(df, header, device)
    frame = frames[0]
    table = filter_time_range(frame["df"], start, end)
    if metric:
        if metric not in table.columns:
            raise ServiceError(
                f"Unknown metric {metric!r}; available: {list(table.columns)}"
            )
        table = table[[metric]]
    meta = {
        "header": header,
        "alias": alias,
        "device": frame["sub_title"] or None,
        "os_details": pl_h2.get_os_details_from_df(df).strip(),
        "restart_headers": pl_h2.get_restart_headers(df),
    }
    return table, meta
