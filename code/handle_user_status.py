import polars as pl
import datetime
import os
from config import Config

def load_df_from_file() -> pl.DataFrame:
    upload_dir = Config.upload_dir
    config_dir = os.path.join(upload_dir, "config")
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    filename = os.path.join(config_dir,"user_df.parquet")
    df = pl.DataFrame()
    if not os.path.exists(filename):
        df = create_user_status_df()
        write_df_to_file(df, filename)
    else:
        df = pl.read_parquet(filename)
    return df, filename

def write_df_to_file(df: pl.DataFrame, filename: str = None) -> None:
    if not filename:
        filename = load_df_from_file()[1]
    df.write_parquet(filename)

def delete_records(df: pl.DataFrame, date: datetime.datetime) -> pl.DataFrame:
    """Deletes records from the dataframe where login_time is greater than the provided date.
    Args:
        df: The dataframe to delete the records from
        date: The date to compare with
    Returns:
        The dataframe with the deleted records
    """
    df = df.filter(df["login_time"] <= date)
    write_df_to_file(df)

def create_user_status_df() -> pl.DataFrame:
    """Creates prefilled dataframe including metadata about
    user login times.
    Args:
        None
    Returns:
        A dataframe with the following columns:
            - user_name: The user's unique ID
            - login_time: When did the user login last time
            - user_status: Does the user exist in the database
    """
    return pl.DataFrame(
        {
            "user_name": ["admin"],
            "login_time": [datetime.datetime.now()],
            "success": [True],
        }
    )

def add_record(
    user_name: str,
    login_time: datetime.datetime,
    success: bool,
) -> pl.DataFrame:
    """Adds a record to the dataframe.
    Args:
        df: The dataframe to add the record to
        user_name: The user's unique ID
        login_time: When did the user login last time
        success: could the user login
    """
    filename = load_df_from_file()[1]
    df = get_user_status_df()
    df1 = pl.DataFrame(
        {
            "user_name": [user_name],
            "login_time": [login_time],
            "success": [success],
        }
    )
    df = df.vstack(df1)
    df.write_parquet(filename)

def get_user_status_df() -> pl.DataFrame:
    """Gets the dataframe with the user status.
    Args:
        None
    Returns:
        The dataframe with the user status
    """
    df = load_df_from_file()[0]
    return df

def remove_old_logins(df: pl.DataFrame, date: datetime.date) -> pl.DataFrame:
    df = df.filter(pl.col("login_time") > date)
    return df