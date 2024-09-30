import re
import io
import subprocess
import os.path
from pathlib import Path
from datetime import datetime
import redis_mng
import polars as pl
import pl_helpers2
import config as Config


def get_file_type(file_path: str) -> str:
    file_type = subprocess.run(
        ["file", "-b", "--mime-type", file_path], capture_output=True, text=True
    ).stdout.strip()
    if "text" in file_type:
        return "ascii"
    return file_type


def check_file_type(file_path: str) -> str:
    file_type = Config.Config.file_type
    file_path = Path(file_path)
    abs_path = file_path.absolute().as_posix()
    extended_path = abs_path + "." + file_type
    if os.path.isfile(abs_path):
        with open(abs_path, "rb") as f:
            header = f.read(4)
            if header == b"PAR1":
                return file_type, abs_path
            else:
                return get_file_type(abs_path), file_path
    elif os.path.isfile(extended_path):
        with open(extended_path, "rb") as f:
            header = f.read(4)
            if header == b"PAR1":
                return file_type, abs_path
            else:
                return get_file_type(extended_path), abs_path
    else:
        assert False, f"file {abs_path} does not exist"


def get_data_frame(file_name, user_name):
    """
    Load structure containing data frames from redis or pickle
    """
    # load from redis
    parquet_file = Path(f"{file_name}.parquet")
    if not os.path.exists(parquet_file):
        parquet_file = Path(file_name)
    rs = redis_mng.get_redis_conn(decode=False)
    basename = os.path.basename(file_name)
    if rs:
        r_item = f"{Config.Config.rkey_pref}:{user_name}"
        file_name_parquet = f"{basename}_parquet"
        parquet_obj = redis_mng.get_redis_val(r_item, property=file_name_parquet)
        parquet_mem = io.BytesIO(parquet_obj)
        try:
            df = pl.read_parquet(parquet_mem)
            print(
                f'{r_item}, {file_name_parquet} \
                loaded from redis at {datetime.now().strftime("%m/%d/%y %H:%M:%S")}'
            )
        except Exception as e:
            print(e)
            try:
                df = pl.read_parquet(parquet_file)
            except Exception as e:
                df = parse_sar_file(parquet_file, user_name, DEBUG=False)
            try:
                parquet_obj = df.to_pandas().to_parquet()
                redis_mng.set_redis_key(
                    parquet_obj,
                    r_item,
                    property=file_name_parquet,
                )
                print(
                    f'{r_item}, {file_name_parquet} saved to redis at {datetime.now().strftime("%m/%d/%y %H:%M:%S")}'
                )
                print(f"{r_item} {file_name_parquet} saved")
            except Exception as e:
                print(
                    f"could not connect to redis server or save {file_name_parquet} to redis server"
                )
                print(f"exception is {e}")
            else:
                return df
    elif os.path.exists(parquet_file):
        try:
            df = pl.read_parquet(parquet_file)
        except Exception as e:
            df = parse_sar_file(parquet_file, user_name, DEBUG=False)
        return df
    else:
        df = parse_sar_file(parquet_file, user_name, DEBUG=False)
    return df


def handle_fibre_and_fs(line: str) -> str:
    am_pm_search = re.compile("AM|PM", re.IGNORECASE)
    tmp_line = line.split()
    change_col = tmp_line[-1]
    if am_pm_search.search(tmp_line[1]):
        ins_index = 2
    else:
        ins_index = 1
    tmp_line.insert(ins_index, change_col)
    tmp_line.pop()
    line = " ".join(tmp_line)
    return line


def parse_sar_file(file_path: str, username: str, DEBUG: bool = False) -> pl.DataFrame:
    file_dict = {}
    df = pl.DataFrame()
    os_details = pl_helpers2.extract_os_details_from_file(file_path)
    content = open(file_path, "r").readlines()
    real_path = Path(file_path).absolute().as_posix()
    parquet_file = Path(f"{real_path}.parquet")

    reg_ignore = re.compile(
        "^(\d{2}:\d{2}:\d{2}.*bus.*idvendor|.*intr.*intr/s|.*temp.*device|.*mhz)",
        re.IGNORECASE,
    )
    reg_delete_us_time = re.compile(" AM | PM ", re.IGNORECASE)
    reg_replace_comma = re.compile("(\d+),(\d+)")
    reg_linux_restart = re.compile("LINUX RESTART")
    reg_time = re.compile("(^\d{2}:\d{2}:\d{2})")
    reg_fibre = re.compile("^(\d{2}:\d{2}:\d{2}.*fch_.*FCHOST)", re.IGNORECASE)
    reg_filesystem = re.compile("^\d{2}:\d{2}:\d{2}.*filesystem", re.IGNORECASE)
    empty_line = re.compile("^\s*$")
    header = False
    header_str = ""
    ignore_data = False
    fc_host = False
    filesystem = False
    restart_field = []
    for line in content:
        if empty_line.search(line):
            header = True
            ignore_data = False
            continue
        if ignore_data:
            continue
        if not reg_time.search(line):
            continue
        if reg_linux_restart.search(line):
            restart_field.append(f"{line} {line.split()[0]}")
            continue
        if header:
            if reg_ignore.search(line):
                ignore_data = True
                header = False
                continue
            if reg_fibre.search(line):
                fc_host = True
                line = handle_fibre_and_fs(line)
            else:
                fc_host = False
            if reg_filesystem.search(line):
                filesystem = True
                line = handle_fibre_and_fs(line)
            header_str = " ".join(line.split()[1:])
            if not file_dict.get(header_str):
                file_dict[header_str] = []
            header = False
        else:
            if fc_host or filesystem:
                line = handle_fibre_and_fs(line)
            file_dict[header_str].append(line)

    for key in file_dict:
        length = len(file_dict[key])
        columns = [
            "header",
            "data",
        ]
        data = [[key] * length, file_dict[key]]
        new_rows = pl.DataFrame(data, schema=columns)
        df = df.vstack(new_rows)
    # create os_details column
    os_precol = pl.Series("os_details", [os_details])
    os_column = pl.Series("os_details", [""] * (len(df) - 1))
    os_column = os_precol.append(os_column)
    df = df.with_columns(os_column)
    # create restart column
    length_restart_field = len(restart_field)
    if length_restart_field > 0:
        restart_precol = pl.Series("restart", restart_field)
        restart_col = pl.Series(
            "Linux_Restart", [""] * (len(df) - length_restart_field)
        )
        restart_col = restart_precol.append(restart_col)
        df = df.with_columns(restart_col)
    # check for AM/PM in time format first row of df column data
    s = df.to_series(1)[0]
    if reg_delete_us_time.search(s):
        TIME_FORMAT = "AM_PM"
    else:
        TIME_FORMAT = "24"
    if reg_replace_comma.search(s):
        df = pl_helpers2.replace_comma_with_point(df, "data")

    df = pl_helpers2.df_clean_data(df, "header")
    df = pl_helpers2.df_reset_date(df, os_details, "data", "date", tformat=TIME_FORMAT)
    df = pl_helpers2.clean_header(df, "header", TIME_FORMAT)
    df = pl_helpers2.df_clean_spaces(df, "data")
    df.write_parquet(parquet_file)
    base_name = os.path.basename(parquet_file)

    rs = redis_mng.get_redis_conn()
    if rs:
        r_item = f"{Config.Config.rkey_pref}:{username}"
        file_name_parquet = f'{base_name.replace(".parquet", "_parquet")}'
        p_obj = redis_mng.get_redis_val(r_item, property=file_name_parquet)
        if not p_obj:
            try:
                mem_obj = df.to_pandas().to_parquet()
                redis_mng.set_redis_key(mem_obj, r_item, property=file_name_parquet)
                print(
                    f'{r_item}, {file_name_parquet} saved to redis at {datetime.now().strftime("%m/%d/%y %H:%M:%S")}'
                )
            except Exception as e:
                print(
                    f"could not connect to redis server or save {file_name_parquet} to redis server",
                )
                print(f"exception is {e}")

    if not DEBUG:
        os.system(f"rm -rf {real_path}")

    return df


if __name__ == "__main__":
    # big
    # my_file = "sar20230605.parquet"
    # my_file = "sar20230605"
    # small
    # restart
    # my_file = "sar20221225-restart.parquet"
    # parquet file
    # my_file= "sar20230620.parquet"
    # ascii file
    my_file = "/data/git/streamlit/sarfile_analyzer_ng/code/sa20231115.txt"
    parse_sar_file(my_file, "test", DEBUG=True)

    print("This should be started as module only")
