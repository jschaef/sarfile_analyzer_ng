import helpers_pl as helpers
import polars as pl
import pl_helpers2 as pl_h2
import re
import alt
import streamlit as st

def prepare_df_for_pandas(df: pl.DataFrame, start: pl.datetime, end: pl.datetime, 
        show_subheaders_for_all:bool=False) -> pl.DataFrame:
    df_field = []
    collect_field = []
    soft_reg = re.compile(r'^SOFT.*', re.IGNORECASE) 
    header_pure = df.columns[1]
    header_tranlated = helpers.translate_headers([header_pure])
    alias = list(header_tranlated.values())[0]
    title = alias
    sub_title = ""
    device_num = 1
    df = pl_h2.get_metrics_from_df(df, header_pure, alias)

    if 'sub_device' not in df.columns:
        df_field.append([df, 0])
    elif (alias == 'CPU' or soft_reg.search(alias)) and not show_subheaders_for_all:
        device = 'all'
        device_df = pl_h2.get_df_from_sub_device(df, 'sub_device', device)
        device_num = len(pl_h2.get_sub_devices_from_df(df, 'sub_device')) -1
        df_field.append([device_df, device])
    else:
        device_list = pl_h2.get_sub_devices_from_df(df, 'sub_device')
        device_list.sort()
        for device in device_list:
            device_df = pl_h2.get_df_from_sub_device(df, 'sub_device', device)
            df_field.append([device_df, device])
            if 'all' in device_list:
                device_num = len(device_list) -1

    for df_tuple in df_field:
        if df_tuple[1]:
            sub_title = df_tuple[1]
        df = df_tuple[0]
        # change that for pl
        if start in df['date'] and end in df['date']:
            df = pl_h2.get_date_df(df, 'date', start, end)
        df = pl_h2.create_metrics_df(df, header_pure)
        df_pandas = df.select(pl.all().shrink_dtype()).to_pandas().set_index('date')
        collect_field.append({'df' :df_pandas, 'title' : title, 'device_num' :
            device_num, 'sub_title' : sub_title})
    return collect_field

def prepare_single_device_for_pandas(df: pl.DataFrame, start: pl.datetime,  
    end: pl.datetime, device: str, file_name:str) -> pl.DataFrame:
    collect_field = []
    header_pure = df.columns[1]
    header_tranlated = helpers.translate_headers([header_pure])
    alias = list(header_tranlated.values())[0]
    title = alias
    sub_title = ""
    device_num = 1
    cached_obj = f"{file_name}{alias}_obj"
    if st.session_state.get(cached_obj, []):
        df = st.session_state[cached_obj][0]
    else:
        df = pl_h2.get_metrics_from_df(df, header_pure, alias)
        helpers.set_state_key(cached_obj, value=df, change_key=file_name)
    device_df = pl_h2.get_df_from_sub_device(df, 'sub_device', device)
    if start in device_df['date'] and end in device_df['date']:
            device_df = pl_h2.get_date_df(device_df, 'date', start, end)
    device_df = pl_h2.create_metrics_df(device_df, header_pure)
    df_pandas = device_df.select(pl.all().shrink_dtype()).to_pandas().set_index('date')
    collect_field.append({'df' :df_pandas, 'title' : title, 'device_num' :
        device_num, 'sub_title' : sub_title})
    return collect_field

def get_device_list(df: pl.DataFrame) -> list:
    header_pure = df.columns[1]
    header_tranlated = helpers.translate_headers([header_pure])
    alias = list(header_tranlated.values())[0]
    first_time = df.to_series(0).unique()[0]
    df = df.filter(pl.col('date') == first_time)
    df = pl_h2.get_metrics_from_df(df, header_pure, alias)
    device_list = pl_h2.get_sub_devices_from_df(df, 'sub_device')
    device_list.sort()
    return device_list

def final_results(df: pl.DataFrame, header:str, statistics: int, os_details: str, 
        restart_headers: list, font_size: int, width: int, height: int, 
        show_metric: int, device_num: int, sub_title: str):
    collect_field = []
    title = header
    if sub_title:
        chart_title = f"{header} {sub_title}"
    else:
        chart_title = title
    dup_bool = 0
    df_describe = 0
    df_display = 0
    metrics = 0
    dup_check = 0

    if statistics:
        df_display = df.copy()
        df_describe = df_display.describe()
        dup_check = df_display[df_display.index.duplicated()]
        # remove duplicate indexes
        if not dup_check.empty:
            dup_bool = 1
            df = df[~df.index.duplicated(keep='first')].copy()
        df_dis = helpers.restart_headers(
            df_display, os_details, restart_headers=restart_headers, display=False)
    else:
        df_dis = pl.DataFrame()
    helpers.restart_headers(
        df, os_details, restart_headers=restart_headers, display=False)

    df = df.reset_index().melt('date', var_name='metrics', value_name='y')
    chart = alt.overview_v1(df, restart_headers, os_details, font_size=font_size,
        width=width, height=height, title=f"{chart_title}")
    if show_metric:
        metrics = df['metrics'].drop_duplicates().tolist()
    collect_field.append({'df' :df, 'chart' : chart, 'title' : title , 
        'metrics' : metrics, 'header': header, 'device_num' : device_num, 
        'dup_bool': dup_bool, 'dup_check' : dup_check, 'df_describe' : 
        df_describe, 'df_stat' : df_dis, 'df_display' : df_display, 
        'sub_title': sub_title })
    return collect_field