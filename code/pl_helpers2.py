import re
import polars as pl
from sqlite2_polars import get_header_from_alias, get_sub_device_from_header


def extract_os_details_from_file(file):
    reg_time = re.compile("^.*\d{2}/\d{2}/\d{2}.*$")
    with open(file, "r") as sar_file:
        for _, line in enumerate(sar_file):
            if "Linux" in line:
                os_details = line.replace("[", "").replace("]", "")
                if reg_time.search(os_details):
                    os_details = re.sub(r'(\d{2}/\d{2}/\d{2,4})', 
                        lambda x: x.group().replace('/', '-'), os_details)
                return os_details


def format_date(os_details: str) -> tuple:
    # presume format 2020-XX-XX for sar operating system details
    date_reg = re.compile("[0-9]{4}-[0-9]{2}-[0-9]{2}")
    date_reg1 = re.compile("[0-9]{2}-[0-9]{2}-[0-9]{2}")
    date_reg2 = re.compile("[0-9]{2}/[0-9]{2}/[0-9]{2}")
    date_reg3 = re.compile("[0-9]{2}/[0-9]{2}/[0-9]{4}")
    date_str = ""
    for item in os_details.split():
        date_str = item
        if date_reg.search(item):
            format = "%Y-%m-%d"
            break
        elif date_reg1.search(item):
            format = "%m-%d-%y"
            break
        elif date_reg2.search(item):
            format = "%m/%d/%y"
            break
        elif date_reg3.search(item):
            format = "%m/%d/%Y"
            break
        else:
            # add fake item
            format = "%Y-%m-%d"
            date_str = "2000-01-01"
    return date_str, format


def df_reset_date(
    df: pl.DataFrame, os_details: str, column_name: str, alias: str, tformat: str = "24"
) -> pl.DataFrame:
    date_str, format = format_date(os_details)
    # Extract the time portion from the column based on the tformat
    if tformat == "AM_PM":
        date_column = df.select(
            pl.col(column_name)
            .str.extract(r"(^\d{2}:\d{2}:\d{2}\s+(AM|PM))")
            .alias(alias)
        )
    else:
        date_column = df.select(
            pl.col(column_name).str.extract(r"(^\d{2}:\d{2}:\d{2})\s+").alias(alias)
        )
    df = df.with_columns(date_column)
    df = df.with_columns(pl.col(alias).str.replace(r"(^.*$)", f"{date_str} $1"))

    if tformat != "AM_PM":
        df = df.with_columns(
            pl.col(alias).str.to_datetime(
                f"{format} %H:%M:%S",
            )
        ).with_columns(pl.col(column_name).str.replace(r"(^\d{2}:\d{2}:\d{2})\s+", ""))
    else:
        df = df.with_columns(
            pl.col(alias).str.to_datetime(
                f"{format} %I:%M:%S %p",
            )
        ).with_columns(
            pl.col(column_name).str.replace(r"(^\d{2}:\d{2}:\d{2}\s+(AM|PM)\s+)", "")
        )
    return df


def df_clean_data(
    df: pl.DataFrame,
    column_name: str,
) -> pl.DataFrame:
    clean_header = get_unwanted_headers()
    condition = ~pl.col(column_name).is_in(clean_header)
    return df.filter(condition)
    #return df


def replace_comma_with_point(df: pl.DataFrame, column_name: str) -> pl.DataFrame:
    df = df.with_columns(pl.col(column_name).str.replace_all(r"(,)", "."))
    return df


def get_unwanted_headers() -> list:
    unwanted_headers = [
        "CPU MHz",
        "INTR intr/s",
    ]
    return unwanted_headers


def get_headers_to_clean() -> list:
    headers_to_clean = [
        "DEV",
        "IFACE",
        "CPU",
        "FCHOST",
        "TTY",
        "FILESYSTEM",
    ]
    return headers_to_clean


def clean_header(df: pl.DataFrame, column_name: str, timeformat: str) -> pl.DataFrame:
    clean_header = get_headers_to_clean()
    pattern = rf"^\s*({'|'.join(clean_header)})\s+"
    df = df.with_columns(pl.col(column_name).str.replace(pattern, ""))
    if timeformat == "AM_PM":
        df = df.with_columns(pl.col(column_name).str.replace(r"^\s*(AM|PM)\s+", ""))
    return df


def df_clean_spaces(df: pl.DataFrame, column_name: str) -> pl.DataFrame:
    df = df.with_columns(
        pl.col(column_name)
        .str.replace(r"\s+", " ")
        .str.rstrip()
        .str.lstrip()
        .str.replace(r"\s+", " ")
   )
    return df


def get_metrics_from_df(df: pl.DataFrame, header: str, alias: str) -> list:
    header_in_db = get_header_from_alias(alias)
    test_header = header if header_in_db == header else header_in_db
    df = df.with_columns(pl.col(header).str.split(" ").alias(header))
    sub_device = get_sub_device_from_header(test_header) 
    if sub_device:
        df = df.with_columns(
            pl.col(header).list.get(0).alias("sub_device"),
            pl.col(header).list.slice(1, -1).alias(header)
        )
    df = df.with_columns(
        pl.col(header).list.eval(
            pl.element().cast(pl.Float32, strict=False).drop_nulls()
        )
    )
    return df


def get_sub_devices_from_df(df: pl.DataFrame, column: str) -> list:
    if column in df.columns:
        return df[column].unique().to_list()
    else:
        return []


def get_df_from_sub_device(
    df: pl.DataFrame, column: str, sub_device: str
) -> pl.DataFrame:
    return df.filter(pl.col(column) == sub_device)


def create_metrics_df(df: pl.DataFrame, column: str) -> pl.DataFrame:
    header_list = column.split()
    for index in range(len(header_list)):
        df = df.with_columns(pl.col(column).list.get(index).alias(header_list[index]))
    df.drop_in_place(column)
    if "sub_device" in df.columns:
        df.drop_in_place("sub_device")
    return df


def create_metric_df(df: pl.DataFrame, column: str, metric: str) -> pl.DataFrame:
    header_list = column.split()
    metric_index = header_list.index(metric)
    df = df.with_columns(pl.col(column).list.get(metric_index).alias(metric))
    df.drop_in_place(column)
    if "sub_device" in df.columns:
        df = df.rename({"sub_device": "device"})
    return df


def create_metric_df2(df: pl.DataFrame, column: str, metric: str) -> pl.DataFrame:
    header_list = column.split()
    metric_index = header_list.index(metric)
    df = df.with_columns(pl.col(column).list.get(metric_index).alias(metric))
    df.drop_in_place(column)
    return df


def get_date_df(
    df: pl.DataFrame, column: str, start: pl.datetime, end: pl.datetime
) -> pl.DataFrame:
    return df.filter(pl.col(column) >= start).filter(pl.col(column) <= end)


def get_headers(df: pl.DataFrame) -> list:
    return df.unique("header")["header"].to_list()


def get_data_frames_from_header(header: str, df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(pl.col("header") == header)


def get_os_details_from_df(df: pl.DataFrame) -> str:
    return df.filter(pl.col("os_details").str.contains("Linux"))[
        "os_details"
    ].to_list()[0]


def get_restart_headers(df: pl.DataFrame) -> list:
    if column_exists(df, "restart"):
        return df.filter(pl.col("restart").str.contains("RESTART"))["restart"].to_list()
    else:
        return []


def column_exists(df: pl.DataFrame, column_name: str) -> bool:
    return column_name in df.columns


def get_data_frames_from__headers(headers: list, df: pl.DataFrame, column: str) -> list:
    df_list = []
    df = df.select(pl.col("*").exclude("os_details", "restart"))
    for header in headers:
        single_df = df.filter(pl.col(column) == header)
        single_df = single_df.select(pl.col("*").exclude("header"))
        single_df = single_df.select(["date", "data"])
        single_df = single_df.rename({"data": header})
        df_list.append(single_df)
    return df_list


def get_complete_dataframe_from_headers(
    headers: list, df: pl.DataFrame, column: str
) -> pl.DataFrame:
    filtered_df = df.filter(pl.col(column).str.contains("|".join(headers)))
    return filtered_df

def filter_df_by_range(
    df: pl.DataFrame, column: str, cval: any, check: str = "lt"
) -> pl.DataFrame:
    if check == "gt":
        return df.filter(pl.col(column) >= cval)
    else:
        return df.filter(pl.col(column) <= cval)


def dataframe_editor(
    df: pl.DataFrame, col: object, index: int, colname: str, checked: bool = False
) -> pl.DataFrame:
    df = df.to_pandas()
    df_with_selections = df.copy()
    df_with_selections.drop_duplicates(inplace=True)
    df_with_selections.insert(index, colname, checked)

    # Get dataframe row-selections from user with st.data_editor
    editor = col.empty()
    edited_df = editor.data_editor(
        df_with_selections,
        hide_index=True,
        disabled=df.columns,
    )

    # Filter the dataframe using the temporary column, then drop the column
    selected_rows = edited_df[edited_df[colname]]
    return selected_rows.drop(colname, axis=1), editor
