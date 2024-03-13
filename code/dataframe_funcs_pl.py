#!/usr/bin/python3

import re
import pandas as pd
import polars as pl
from datetime import timedelta
import streamlit as st
def format_date(os_details):
    # presume format 2020-XX-XX for sar operating system details
    date_reg = re.compile("[0-9]{4}-[0-9]{2}-[0-9]{2}")
    date_reg1 = re.compile("[0-9]{2}-[0-9]{2}-[0-9]{2}")
    date_reg2 = re.compile("[0-9]{2}/[0-9]{2}/[0-9]{2}$")
    date_reg3 = re.compile("[0-9]{2}/[0-9]{2}/[0-9]{4}")
    date_str = ""
    for item in os_details.split():
        date_str = item
        if date_reg.search(item):
            format = "%Y-%m-%d"
            break
        elif date_reg1.search(item):
            format = "%m-%d-%y %H:%M:%S"
            break
        elif date_reg2.search(item):
            format = "%m/%d/%y %H:%M:%S"
            break
        elif date_reg3.search(item):
            format = "%m/%d/%Y %H:%M:%S"
            break
        else:
            # add fake item
            format = "%Y-%m-%d"
            date_str = "2000-01-01"
    return (date_str, format)


def translate_dates_into_list(df: pl.DataFrame):
    date_series = df["date"]
    if not date_series.is_empty():
        minute = date_series[0].minute
        hours = [date for date in date_series[0:] if date.minute <= minute - 1]
        hours.insert(0, date_series[0])
        hours.append(date_series[-1])
        return hours
    else:
        return []

def insert_restarts_into_df(os_details, df, restart_headers):
    # date_str like 2020-09-17
    date_str, _ = format_date(os_details)
    new_rows = []
    for header in restart_headers:
        # restart_headers have time of restart appended as last string
        # hour time, e.g.: 10:13:47
        h_time = header.split()[-1]
        z = pd.to_datetime(f"{date_str} {h_time}", format="mixed")
        ind = 0
        for x in range(len(df.index)):
            # check if date - z is the minimum
            if (z - df.index[x]).total_seconds() > 0:
                continue
            # same index as restart exists
            elif (z - df.index[x]).total_seconds() == 0:
                z = z + timedelta(seconds=10)
            else:
                ind = x - 1
                break
        # Reboot is last entry
        if len(df.index) > 0:
            if ind == 0:
                ind = len(df.index) - 1
            # restart row date first entry
            elif ind < 0:
                ind = 0
            rind = df.index[ind]
            # copy last line before restart, reindex it and insert the reboot str
            reset_row = df.loc[[rind]]
            reset_row = reset_row.reindex([z])
            reset_row.loc[z] = 0.00
            new_rows.append(reset_row)
            df = insert_row(ind, df, reset_row)
    return df, new_rows


# example from https://pythoninoffice.com/insert-rows-into-a-dataframe/
def insert_row(row_num, orig_df, row_to_add):
    if row_num == 0:
        df_final = pd.concat([row_to_add, orig_df], ignore_index=False)
    elif len(orig_df.index) - 1 > row_num:
        # split original data frame into two parts and insert the restart pd.series
        row_num = min(max(0, row_num), len(orig_df))
        df_part_1 = orig_df[orig_df.index[0] : orig_df.index[row_num]]
        df_part_2 = orig_df[orig_df.index[row_num + 1] : orig_df.index[-1]]
        df_final = pd.concat([df_part_1, row_to_add, df_part_2], ignore_index=False)
    else:
        df_final = pd.concat([orig_df, row_to_add], ignore_index=False)
    return df_final


def replace_ymt(start_date, end_date, df):
    """replaces year, month, day in start_date and/or end_date

    Args:
        start_date (date_object): the date object which is used as start
        end_date (date_object): the date object which is used as end
        df: pandas dataframe
    Returns:
        start, end with same year, month, day as dataframe
    """
    df = df.copy()

    s_field = [s_year, s_month, s_day] = (
        start_date.year,
        start_date.month,
        start_date.day,
    )
    e_field = [e_year, e_month, e_day] = end_date.year, end_date.month, end_date.day
    df_field = [df_year, df_month, df_day] = (
        df.index[0].year,
        df.index[0].month,
        df.index[0].day,
    )
    if s_field != df_field:
        start_date = start_date.replace(year=df_year, month=df_month, day=df_day)
    if e_field != df_field:
        end_date = end_date.replace(year=df_year, month=df_month, day=df_day)
    return start_date, end_date
