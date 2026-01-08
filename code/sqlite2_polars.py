import re
import io
import sql_stuff
import polars as pl
from streamlit import cache_data
import redis_mng
from functools import lru_cache


@lru_cache(maxsize=32)
def _get_table_df_threadsafe(table_name: str):
    """Thread-safe table loader.

    Important: This is used from ThreadPoolExecutor workers.
    We intentionally avoid Streamlit's caching here to prevent
    'missing ScriptRunContext' warnings.
    """
    parquet_obj = redis_mng.get_redis_val(table_name, property=table_name)
    if parquet_obj:
        parquet_mem = io.BytesIO(parquet_obj)
    else:
        parquet_mem = io.BytesIO(b"")

    try:
        df = pl.read_parquet(parquet_mem)
    except Exception:
        data_db = sql_stuff.find_db()
        connection_uri = f"sqlite:///{data_db}"
        query = f"select * from {table_name}"
        df = pl.read_database_uri(query=query, uri=connection_uri)
        redis_df = redis_mng.convert_df_for_redis(df)
        redis_mng.set_redis_key(redis_df, table_name, property=table_name)
    return df


@cache_data
def get_table_df(table_name: str):
    parquet_obj = redis_mng.get_redis_val(table_name, property=table_name)
    if parquet_obj:
        parquet_mem = io.BytesIO(parquet_obj)

    else:
        parquet_mem = io.BytesIO(b'')

    try:
        df = pl.read_parquet(parquet_mem)
        print(
        fr'{table_name} loaded from redis'
        )
    except Exception as e:
        data_db = sql_stuff.find_db()
        connection_uri = f"sqlite:///{data_db}"
        query = f"select * from {table_name}"
        df = pl.read_database_uri(query=query, uri=connection_uri)
        redis_df = redis_mng.convert_df_for_redis(df)
        redis_mng.set_redis_key(redis_df, table_name, property=table_name)
    return df


def get_col_list_from_filter(
    df: pl.DataFrame, column: str, filter: str, return_column: str
) -> list:
    return df.filter(pl.col(column).str.contains(filter))[return_column].to_list()


def get_exact_value_from_filter(
    df: pl.DataFrame, column: str, filter: str, return_column: str
) -> any:
    result_series = df[column].eq(filter)
    if result_series.any():
        return df.filter(result_series)[return_column].to_list()[0]
    else:
        return None


@cache_data
def ret_metric_description(
    metric: str,
) -> str:
    df = get_table_df("metric")
    description = f"no description found for {metric}"
    result_series = df["metric"].eq(metric)
    if result_series.any():
        description = df.filter(result_series)["description"].to_list()[0]
    return description


@cache_data
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

@cache_data
def get_header_prop(header, property):
    # check if exact header is in df
    headings_df = get_table_df("headingstable")
    result_series = headings_df["header"].eq(header)
    if result_series.any():
        property = headings_df.filter(result_series)[property].to_list()[0]
        return property
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


@lru_cache(maxsize=4096)
def get_header_from_alias(alias):
    headings_df = _get_table_df_threadsafe("headingstable")
    return get_exact_value_from_filter(headings_df, "alias", alias, "header")

@lru_cache(maxsize=4096)
def get_sub_device_from_header(header):
    headings_df = _get_table_df_threadsafe("headingstable")
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
