"""Headless service layer: reuses the pure data functions from code/.

Everything here works without a Streamlit session. The functions mirror what
mng_sar.py / single_file_pl.py / dia_overview_pl.py / multi_files_pl.py do in
the UI, minus widgets and st.session_state.
"""

import datetime
import logging
import os
import re
import time
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

# Usernames may be plain logins or e-mail addresses. The first character must
# be alphanumeric, which rules out '.', '..' and hidden names - important
# because the username becomes a directory under UPLOAD_DIR. Path separators
# are not part of the character class, so traversal is impossible.
USERNAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._@+-]*$"
_SAFE_USERNAME = re.compile(USERNAME_PATTERN)


class ServiceError(Exception):
    """Raised for user-facing errors (bad file name, unknown header, ...)."""


class _LogCol:
    """Stand-in for the Streamlit column object rename_sar_file writes to."""

    def info(self, msg):
        logger.info(msg)

    def warning(self, msg):
        logger.warning(msg)


def user_dir(username: str) -> Path:
    # Defense in depth: usernames reach this from signed tokens, but the
    # directory is built from them, so validate here as well.
    if not _SAFE_USERNAME.match(username):
        raise ServiceError(f"Invalid username: {username!r}")
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


# ---------------------------------------------------------------------------
# admin / maintenance: per-user disk usage and age-based cleanup
# ---------------------------------------------------------------------------
# upload/config is a sibling of the user directories but holds shared state
# (login history/counter, the headingstable/metric table caches) - it must
# never appear in per-user reports or be touched by the cleanup.
EXCLUDED_UPLOAD_DIRS = {"config"}


def _existing_user_dir(username: str) -> Path:
    """Like user_dir(), but read-only: no mkdir side effect.

    user_dir() creates the directory, which is right for uploads but wrong
    for admin scans - scanning must not litter UPLOAD_DIR with empty dirs.
    """
    if not _SAFE_USERNAME.match(username):
        raise ServiceError(f"Invalid username: {username!r}")
    directory = Path(Config.upload_dir) / username
    if not directory.is_dir():
        raise ServiceError(f"No upload directory for user {username!r}")
    return directory


def _file_age_days(path: Path, name: str, now: float) -> tuple[float, str]:
    """Age of one file in days, preferring the upload date in the name.

    Uploads are renamed to '<upload date>_<host>_<sar date>' (helpers_pl.
    rename_sar_file), so the first 10 characters carry when the file reached
    the server - that survives copies, unlike mtime. Files that don't follow
    the convention fall back to st_mtime.
    """
    try:
        upload_date = datetime.date.fromisoformat(name[:10])
        return (datetime.date.today() - upload_date).days, "name"
    except ValueError:
        return (now - path.stat().st_mtime) / 86400, "mtime"


def disk_usage_report() -> dict:
    """Per-user disk usage below UPLOAD_DIR, largest consumers first."""
    import sql_stuff

    base = Path(Config.upload_dir)
    known_users = set(sql_stuff.view_all_users(kind="list"))
    users = []
    for entry in sorted(base.iterdir()) if base.is_dir() else []:
        if not entry.is_dir() or entry.name in EXCLUDED_UPLOAD_DIRS:
            continue
        record = {
            "username": entry.name,
            "total_bytes": 0,
            "file_count": 0,
            "sar_bytes": 0,
            "pdf_bytes": 0,
            "pdf_count": 0,
            "tmp_bytes": 0,
            "tmp_count": 0,
            # Directory left behind by a deleted account (self_service used
            # to keep them) - safe to clean, impossible to log into.
            "orphan_user": entry.name not in known_users,
        }
        for root, _dirs, files in os.walk(entry, followlinks=False):
            # anywhere below <user>/pdf counts as pdf - older app versions
            # created one sub-directory per chart under pdf/
            in_pdf = "pdf" in Path(root).relative_to(entry).parts
            for file_name in files:
                try:
                    size = (Path(root) / file_name).stat().st_size
                except OSError:
                    continue  # race: deleted meanwhile, broken symlink, ...
                record["total_bytes"] += size
                record["file_count"] += 1
                if in_pdf:
                    record["pdf_bytes"] += size
                    record["pdf_count"] += 1
                elif file_name.startswith(".tmp_"):
                    record["tmp_bytes"] += size
                    record["tmp_count"] += 1
                else:
                    record["sar_bytes"] += size
        # Directories with no file anywhere beneath them (counted bottom-up
        # so a dir holding only empty dirs is empty too) - legacy per-chart
        # dirs under pdf/ show up here.
        non_empty: set[str] = set()
        empty_dirs = 0
        for root, dirs, files in os.walk(entry, topdown=False, followlinks=False):
            if files or any(os.path.join(root, d) in non_empty for d in dirs):
                non_empty.add(root)
            elif Path(root) != entry:
                empty_dirs += 1
        record["empty_dir_count"] = empty_dirs
        users.append(record)

    users.sort(key=lambda u: u["total_bytes"], reverse=True)
    return {
        "upload_dir": str(base.resolve()),
        "total_bytes": sum(u["total_bytes"] for u in users),
        "total_files": sum(u["file_count"] for u in users),
        "users": users,
    }


def _collect_cleanup_candidates(directory: Path, days: int, now: float) -> list[dict]:
    """What cleanup_old_files would remove for one user - shared by dry run
    and real run so the preview always matches the action."""
    candidates = []

    # SAR files: raw + .parquet share a base name and form one unit - never
    # delete one half (list_sar_files dedupes the same way).
    entries = [e for e in directory.iterdir() if e.is_file()]
    bases: dict[str, list[Path]] = {}
    for entry in entries:
        if entry.name.startswith("."):
            continue
        bases.setdefault(entry.name.removesuffix(".parquet"), []).append(entry)
    for base_name, members in sorted(bases.items()):
        age, source = _file_age_days(members[0], base_name, now)
        if source == "mtime":
            # Unparsable name: judge the pair by its NEWEST member so a
            # half-fresh pair is never deleted.
            age = min(_file_age_days(m, "", now)[0] for m in members)
        if age > days:
            candidates.append(
                {
                    "name": base_name,
                    "kind": "sar",
                    "size_bytes": sum(m.stat().st_size for m in members),
                    "age_days": round(age, 1),
                    "age_source": source,
                }
            )

    # Generated PDFs: no naming convention, mtime is all there is. Walk the
    # whole pdf/ subtree - older app versions created one directory per chart.
    pdf_dir = directory / "pdf"
    if pdf_dir.is_dir():
        for root, _dirs, files in os.walk(pdf_dir, followlinks=False):
            for file_name in sorted(files):
                path = Path(root) / file_name
                age = (now - path.stat().st_mtime) / 86400
                if age > days:
                    candidates.append(
                        {
                            "name": str(path.relative_to(directory)),
                            "kind": "pdf",
                            "size_bytes": path.stat().st_size,
                            "age_days": round(age, 1),
                            "age_source": "mtime",
                        }
                    )
        # Empty directories below pdf/ are dead weight (legacy per-chart
        # dirs); collected bottom-up so children are removed before parents.
        non_empty: set[str] = set()
        for root, dirs, files in os.walk(pdf_dir, topdown=False, followlinks=False):
            if files or any(os.path.join(root, d) in non_empty for d in dirs):
                non_empty.add(root)
            elif Path(root) != pdf_dir:
                candidates.append(
                    {
                        "name": str(Path(root).relative_to(directory)),
                        "kind": "emptydir",
                        "size_bytes": 0,
                        "age_days": round((now - Path(root).stat().st_mtime) / 86400, 1),
                        "age_source": "mtime",
                    }
                )

    # Orphaned upload temp files (crashed/aborted uploads): always. A live
    # upload's temp file exists only for the split second before renaming.
    for entry in sorted(entries):
        if entry.name.startswith(".tmp_"):
            candidates.append(
                {
                    "name": entry.name,
                    "kind": "tmp",
                    "size_bytes": entry.stat().st_size,
                    "age_days": round((now - entry.stat().st_mtime) / 86400, 1),
                    "age_source": "mtime",
                }
            )
    return candidates


def cleanup_old_files(
    days: int = 30, username: str | None = None, dry_run: bool = True
) -> dict:
    """Delete uploads older than `days` days (plus orphaned temp files).

    Age comes from the upload-date prefix in the file name where possible
    (see _file_age_days). SAR raw/parquet pairs go through delete_sar_file so
    the cached dataframe in Redis is dropped too - leaving it behind would
    keep serving deleted data. dry_run returns the identical structure
    without touching anything.
    """
    base = Path(Config.upload_dir)
    if username is not None:
        targets = [_existing_user_dir(username)]
    else:
        targets = [
            e
            for e in (sorted(base.iterdir()) if base.is_dir() else [])
            if e.is_dir() and e.name not in EXCLUDED_UPLOAD_DIRS
        ]

    now = time.time()
    per_user, errors = [], []
    deleted_bytes = deleted_files = 0
    for directory in targets:
        user = directory.name
        candidates = _collect_cleanup_candidates(directory, days, now)
        if not candidates:
            continue
        if not dry_run:
            for entry in candidates:
                try:
                    if entry["kind"] == "sar":
                        delete_sar_file(user, entry["name"])
                    elif entry["kind"] == "emptydir":
                        (directory / entry["name"]).rmdir()
                    else:  # pdf/... or .tmp_<name>
                        (directory / entry["name"]).unlink(missing_ok=True)
                    deleted_bytes += entry["size_bytes"]
                    deleted_files += 1
                except (ServiceError, OSError) as exc:
                    errors.append(
                        {"username": user, "name": entry["name"], "detail": str(exc)}
                    )
            # Deleting old PDFs can leave their per-chart directories empty -
            # prune those too (bottom-up; rmdir refuses non-empty dirs, which
            # is exactly the safety we want). pdf/ itself stays.
            pdf_dir = directory / "pdf"
            if pdf_dir.is_dir():
                for root, _dirs, _files in os.walk(
                    pdf_dir, topdown=False, followlinks=False
                ):
                    if Path(root) != pdf_dir:
                        try:
                            Path(root).rmdir()
                        except OSError:
                            pass
        per_user.append(
            {
                "username": user,
                "files": candidates,
                "bytes": sum(c["size_bytes"] for c in candidates),
                "count": len(candidates),
            }
        )

    return {
        "dry_run": dry_run,
        "days": days,
        "users": per_user,
        "total_bytes": sum(u["bytes"] for u in per_user),
        "total_files": sum(u["count"] for u in per_user),
        "deleted_bytes": deleted_bytes,
        "deleted_files": deleted_files,
        "errors": errors,
    }
