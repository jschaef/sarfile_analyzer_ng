import helpers_pl as helpers
import polars as pl
import pandas as pd
import pl_helpers2 as pl_h2
import dataframe_funcs_pl as dff
import re
import streamlit as st
import bokeh_charts

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
        
        # Pre-calculate statistics in Polars (much faster than Pandas .describe())
        stats_pl = None
        if df.width > 1:
            # Filter out non-numeric columns and calculate describe
            numeric_cols = [c for c, t in zip(df.columns, df.dtypes) if t.is_numeric()]
            if numeric_cols:
                stats_pl = df.select(numeric_cols).describe()
        
        df_pandas = df.to_pandas().set_index('date')
        collect_field.append({
            'df' :df_pandas, 
            'title' : title, 
            'device_num' : device_num, 
            'sub_title' : sub_title,
            'stats_pl': stats_pl
        })
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
    df_pandas = device_df.to_pandas().set_index('date')
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

def final_results(df: pd.DataFrame, header:str, statistics: int, os_details: str, 
        restart_headers: list, font_size: int, width: int, height: int, 
        show_metric: int, device_num: int, sub_title: str, stats_pl=None,
        precompute_chart=False) -> list:
    collect_field = []
    title = header
    dup_bool = 0
    df_describe = 0
    df_display = 0
    metrics = 0
    dup_check = 0
    restart_index = []

    if statistics:
        df_display = df.copy()
        if stats_pl is not None:
             # Use the pre-calculated Polars stats converted to Pandas
             df_describe = stats_pl.to_pandas()
             if 'statistic' in df_describe.columns:
                 df_describe = df_describe.set_index('statistic')
        else:
             df_describe = df_display.describe()
             
        dup_check = df_display[df_display.index.duplicated()]
        # remove duplicate indexes
        if not dup_check.empty:
            dup_bool = 1
            df = df[~df.index.duplicated(keep='first')].copy()
            
        if restart_headers:
            df_dis, restart_index = helpers.restart_headers_plain_with_rows(
                df_display, os_details, restart_headers=restart_headers)
        else:
            df_dis = df_display
            restart_index = []
    else:
        df_dis = pd.DataFrame() 
        
    # Correctly insert restart markers into the DataFrame used for plotting
    if restart_headers:
        df, _ = dff.insert_restarts_into_df(os_details, df, restart_headers)

    # NO LONGER MELT here. bokeh_charts.overview_v1 supports wide format.
    # df = df.reset_index().melt('date', var_name='metrics', value_name='y')
    
    # We still need a metrics list for display purposes in some tabs
    if show_metric:
        metrics = [c for c in df.columns if c != 'date']
        
    precomputed_chart = None
    if precompute_chart:
        # Pre-calculating chart here (will run in ThreadPoolExecutor)
        # ensures the main Streamlit thread is not blocked by Bokeh figure generation.
        try:
            chart_html, bokeh_fig = bokeh_charts.overview_v1(
                df,
                restart_headers,
                os_details,
                font_size=font_size,
                width=width,
                height=height,
                title=f"{header} {sub_title}" if sub_title else f"{header}",
            )
            precomputed_chart = (chart_html, bokeh_fig)
        except Exception:
            pass

    collect_field.append({
        'df' :df, 
        'title' : title , 
        'metrics' : metrics, 
        'header': header, 
        'device_num' : device_num, 
        'dup_bool': dup_bool, 
        'dup_check' : dup_check, 
        'df_describe' : df_describe, 
        'df_stat' : df_dis, 
        'df_display' : df_display, 
        'sub_title': sub_title, 
        'restart_index': restart_index,
        'precomputed_chart': precomputed_chart
    })
    return collect_field