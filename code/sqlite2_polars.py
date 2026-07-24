import os
import re
import sql_stuff
import polars as pl
from functools import lru_cache
from handle_user_status import atomic_write_parquet, get_config_dir

# Tables cached on disk. SQLite stays the single source of truth; these
# parquet files are a derived copy that every process (UI, API, MCP server)
# shares through the upload/config directory - no Redis involved, so the
# cache also works when Redis is absent.
CACHED_TABLES = ("headingstable", "metric")


def table_parquet_path(table_name: str) -> str:
    return os.path.join(get_config_dir(), f"{table_name}.parquet")


def _table_mtime(table_name: str) -> int:
    """Modification time of the cached file, 0 when it does not exist.

    Used as part of every cache key: when any process rewrites the file, the
    key changes and all other processes reload on their next access. That is
    what makes the cache consistent across processes without Redis.
    """
    try:
        return os.stat(table_parquet_path(table_name)).st_mtime_ns
    except OSError:
        return 0


def refresh_table_parquet(table_name: str) -> pl.DataFrame:
    """Rebuild the cached parquet file from SQLite and return the table."""
    connection_uri = f"sqlite:///{sql_stuff.data_db}"
    df = pl.read_database_uri(query=f"select * from {table_name}", uri=connection_uri)
    atomic_write_parquet(df, table_parquet_path(table_name))
    return df


@lru_cache(maxsize=16)
def _read_table(table_name: str, mtime: int) -> pl.DataFrame:
    """Read one table; `mtime` is only part of the cache key (see above)."""
    if mtime:
        try:
            return pl.read_parquet(table_parquet_path(table_name))
        except Exception:
            pass  # missing or damaged - fall through and rebuild it
    return refresh_table_parquet(table_name)


def get_table_df(table_name: str) -> pl.DataFrame:
    return _read_table(table_name, _table_mtime(table_name))


# Kept as an alias: callers in worker threads used to need a separate,
# Streamlit-free loader. Nothing here touches Streamlit anymore.
_get_table_df_threadsafe = get_table_df


def refresh_all_tables() -> None:
    """Rebuild every cached table from SQLite - call this on process start."""
    for table_name in CACHED_TABLES:
        try:
            refresh_table_parquet(table_name)
        except Exception:
            pass  # empty/missing DB must not stop the app from starting
    _clear_memory_caches()


def _clear_memory_caches() -> None:
    for cached in (
        _read_table,
        _headings_dict,
        _alias_to_header_dict,
        _metrics_dict,
        _header_prop,
        _sub_device_from_header,
    ):
        cached.cache_clear()


def invalidate_table_cache(table_name: str) -> None:
    """Rebuild a table's cached copy after it was written to in SQLite.

    Every write path (Manage Headings, Manage Metrics, the seed maintenance
    in deploy.sh) has to call this, otherwise the change stays invisible to
    the running processes.
    """
    refresh_table_parquet(table_name)
    _clear_memory_caches()


def get_exact_value_from_filter(
    df: pl.DataFrame, column: str, filter: str, return_column: str
) -> any:
    result_series = df[column].eq(filter)
    if result_series.any():
        return df.filter(result_series)[return_column].to_list()[0]
    else:
        return None


@lru_cache(maxsize=8)
def _metrics_dict(mtime: int) -> dict:
    """The whole metrics table as a dictionary for O(1) lookups."""
    df = _read_table("metric", mtime)
    return dict(zip(df["metric"].to_list(), df["description"].to_list()))


def ret_metric_description(
    metric: str,
) -> str:
    m_dict = _metrics_dict(_table_mtime("metric"))
    return m_dict.get(metric, f"no description found for {metric}")


def view_all_metrics() -> list:
    df = get_table_df("metric")
    m_list = []
    values = df.select(["metric", "description"])
    metric_list = values["metric"]
    desc_list = values["description"]
    for x, y in zip(metric_list, desc_list):
        m_list.append([x, y])
    return m_list


def ret_all_headers(df, kind: str = "return"):
    h_list = []
    df = df.select(pl.exclude("id"))
    if kind == "show":
        x = list(df)
        values = zip(*x)
        for header, description, alias, keywd in values:
            h_list.append([header, description, alias, keywd])
    else:
        for header in df.select("header")["header"].to_list():
            h_list.append(header)
    return h_list

def ret_all_aliases(df):
    a_list = []
    df = df.select(pl.exclude("id"))
    for alias in df.select("alias")["alias"].to_list():
        a_list.append(alias)
    return a_list

@lru_cache(maxsize=16)
def _headings_dict(property_name: str, mtime: int) -> dict:
    """One property of the headings table as a dictionary."""
    df = _read_table("headingstable", mtime)
    return dict(zip(df["header"].to_list(), df[property_name].to_list()))


def get_header_prop(header, property):
    return _header_prop(header, property, _table_mtime("headingstable"))


@lru_cache(maxsize=4096)
def _header_prop(header, property, mtime):
    # Try exact match via dictionary lookup first
    h_dict = _headings_dict(property, mtime)
    if header in h_dict:
        return h_dict[header]

    # Fallback to expensive fuzzy search only if exact match fails
    headings_df = _read_table("headingstable", mtime)
    # check if exact header is in df
    result_series = headings_df["header"].eq(header)
    if result_series.any():
        property_val = headings_df.filter(result_series)[property].to_list()[0]
        return property_val
    # header differs from headers in df
    else:
        header_result_list = []
        all_headers = ret_all_headers(headings_df)
        org_header = header
        org_header_items = org_header.split()
        length_header = len(org_header_items)
        for entry in all_headers:
            # max first 2 metric checks in header
            end_slice = 2 if length_header >= 2 else 1
            for metric in org_header_items[0:end_slice]:
                if metric in entry:
                    header_result_list.append(entry)
                    break
        if len(header_result_list) == 1:
            # one header found which differs slightly from original
            result_series = headings_df["header"].eq(header_result_list[0])
            property = headings_df.filter(result_series)[property].to_list()[0]
            return property
        else:
            # multiple header with same metric, e.g. %usr
            col_field = []
            for header_result in header_result_list:
                counter = 0
                for item in org_header_items:
                    if item in header_result:
                        # count how much different items compared to header
                        counter += 1
                col_field.append([header_result, counter])
            if col_field:
                best_result = max(col_field, key=lambda x: x[1])[0]
                result_series = headings_df["header"].eq(best_result)
                property = headings_df.filter(result_series)[property].to_list()[0]
                return property
            else:
                return org_header


@lru_cache(maxsize=8)
def _alias_to_header_dict(mtime: int) -> dict:
    """Alias to header mapping as a dictionary."""
    df = _read_table("headingstable", mtime)
    return dict(zip(df["alias"].to_list(), df["header"].to_list()))


def get_header_from_alias(alias):
    return _alias_to_header_dict(_table_mtime("headingstable")).get(alias)


def get_sub_device_from_header(header):
    return _sub_device_from_header(header, _table_mtime("headingstable"))


@lru_cache(maxsize=4096)
def _sub_device_from_header(header, mtime):
    headings_df = _read_table("headingstable", mtime)
    ret_search = re.compile(r"(False.*)|(None.*)", re.IGNORECASE)
    keywd = get_exact_value_from_filter(headings_df, "header", header, "keywd")
    if not keywd:
        alias_search = get_possible_alias_from_filter(
            headings_df,
            "header",
            header,
        )
        return alias_search
    else:
        if ret_search.search(keywd):
            return False
        return keywd

def get_possible_alias_from_filter(
    df: pl.DataFrame,
    column: str,
    filter: str,
) -> bool:
    ret_search = re.compile(r"(False.*)|(None.*)", re.IGNORECASE)
    collect_dict = {}
    alias = ""
    for item in filter.split():
        result_field = df[column].str.contains(fr"^\s*{item}\>\s*|\s+\<{item}\>\s+|\s+\<{item}\>\s*$|{item}\>\s*").to_list()
        for index in range(len(result_field)):
            if result_field[index]:
                res_df = df.slice(index, 1)
                alias = res_df["alias"][0]
                if not collect_dict.get(alias, None):
                    collect_dict[alias] = 1
                else:
                    collect_dict[alias] = collect_dict[alias] + 1

    max_value = collect_dict[alias]
    
    if max_value >= len(filter.split()) - 1:
        keywd = get_exact_value_from_filter(df, "alias", alias, "keywd")
        if keywd and not ret_search.search(keywd):
            return True
    else:
        return False
