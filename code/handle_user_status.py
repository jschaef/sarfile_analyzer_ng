import polars as pl
import datetime
import os
from config import Config

# User whose successful logins must not be counted (the app owner).
COUNTER_EXCLUDED_USER = "jschaef"

def get_config_dir() -> str:
    """Returns the config directory below the upload dir, creating it if needed."""
    config_dir = os.path.join(Config.upload_dir, "config")
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    return config_dir

def load_df_from_file() -> pl.DataFrame:
    config_dir = get_config_dir()
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

def load_counter_from_file() -> tuple[pl.DataFrame, str]:
    """Loads the login-counter dataframe, creating it (count = 0) if missing.
    Returns:
        A tuple of the dataframe (single column "count") and its filename.
    """
    config_dir = get_config_dir()
    filename = os.path.join(config_dir, "login_counter.parquet")
    if not os.path.exists(filename):
        df = pl.DataFrame({"count": [0]})
        df.write_parquet(filename)
    else:
        df = pl.read_parquet(filename)
    return df, filename

def get_login_counter() -> int:
    """Returns the current number of counted successful logins."""
    df = load_counter_from_file()[0]
    return int(df["count"][0])

def increment_login_counter(user_name: str) -> int:
    """Increments the successful-login counter by one and persists it.
    Logins of COUNTER_EXCLUDED_USER (the app owner) are not counted.
    Args:
        user_name: The user who just logged in successfully.
    Returns:
        The counter value after this call.
    """
    df, filename = load_counter_from_file()
    count = int(df["count"][0])
    if user_name == COUNTER_EXCLUDED_USER:
        return count
    count += 1
    pl.DataFrame({"count": [count]}).write_parquet(filename)
    return count