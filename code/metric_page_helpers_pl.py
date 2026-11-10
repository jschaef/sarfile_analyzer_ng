import helpers_pl as helpers
import streamlit as st
from config import Config as config
import layout_helper_pl as lh
import polars as pl
import pl_helpers2 as pl_h2
from config import Config
from streamlit.delta_generator import DeltaGenerator

def build_diff_metrics_menu(headers: list, sub_device_dict, df_complete: pl.DataFrame, 
        filename: str, os_details , reboot_headers) -> tuple:
    counter = 0
    collect_field = []
    chart_field = []
    key_pref = 'd_metrics'
    max_cols = config.max_header_count
    cols_per_line = config.cols_per_line
    headers_dict_pure = helpers.translate_headers(headers)
    headers_dict_alias= {v: k for k, v in headers_dict_pure.items()}
    counter = 0

    col1, col2, _, _ = lh.create_columns(4, [0,0,1,1]) 
    st.markdown('___')
    max_cols = config.max_header_count if len(headers_dict_alias) > max_cols else len(headers_dict_alias)
    index = int(max_cols/2)
    # if we have only a few headers to show
    
    col1.write(f'Choose up to {max_cols} different metrics below to compare')
    header_count = col2.selectbox(f'How many header to compare? Max \
        {max_cols} of {len(headers_dict_alias)}', [ x for x in range(1, max_cols + 1)],
        index=index)
    header_cols = header_count

    grid = st.grid(cols_per_line)
    full_lines = header_cols // cols_per_line
    prop_item_dict = {}
    for counter in range(header_cols):
        # a device offers each metric once per line of cols_per_line boxes;
        # an incomplete last line continues the line before it
        if counter % cols_per_line == 0 and counter // cols_per_line < full_lines:
            prop_item_dict = {}
        cell = grid.cell()
        df, prop = display_diff_sboxes(cell, counter, headers_dict_alias, sub_device_dict,
            prop_item_dict, df_complete, key_pref, filename)
        collect_field, chart_field = build_metric_dataframes(df, prop,
            filename, chart_field, collect_field, col=cell,
            os_details=os_details, restart_headers=reboot_headers)
    return collect_field, chart_field


def display_diff_sboxes(r_col: DeltaGenerator, counter: int, alias_dict: dict,
        sub_item_dict: dict, prop_item_dict: dict, df_complete: pl.DataFrame, 
        key_pref: str, filename: str) -> tuple:
    sub_item = 0
    s_header = r_col.selectbox('Choose Header', sorted(alias_dict.keys()), 
        key=f'{key_pref}{counter}')
    s_header_pure = alias_dict[s_header]
    header_df = pl_h2.get_complete_dataframe_from_headers([s_header_pure],
        df_complete, "header")
    metrics = s_header_pure.split()

    if s_header in sub_item_dict.values():
        first_time = header_df.get_column('date')[0]
        date_df = pl_h2.get_date_df(header_df, 'date',first_time, first_time)
        devices_df = pl_h2.get_data_frames_from__headers([s_header_pure], date_df,
            "header")[0]
        devices_df = pl_h2.get_metrics_from_df(devices_df, s_header_pure, s_header)
        device_list = pl_h2.get_sub_devices_from_df(devices_df, 'sub_device')   
        device_list.sort()

        if 'all' in device_list:
            device_list.remove('all')
            device_list.sort()
            device_list.insert(0, 'all')

        if not sub_item_dict.get(s_header, None):
            sub_item = r_col.selectbox('Coose devices', device_list, key=f'sub{counter}')
            sub_item_dict[s_header] = [sub_item]

        else:
            sub_item = r_col.selectbox('Coose devices', [sub_item_dict[s_header][0]], 
                key=f'sub{counter}')
        if not prop_item_dict.get(sub_item, None):
            prop = r_col.selectbox(
                'metric', metrics, key=f'prop_{counter}')
            prop_item_dict[sub_item] = [prop]
        else:
            prop = r_col.selectbox(
                'metric', [x for x in metrics if x not in 
                           prop_item_dict[sub_item]], key=f'prop_{counter}')
            prop_item_dict[sub_item].append(prop)
    else:
        if not prop_item_dict.get(sub_item, None):
            prop = r_col.selectbox(
                'metric', metrics, key=f'prop_{counter}')
            prop_item_dict[sub_item] = [prop]
        else:
            prop = r_col.selectbox(
                'metric', [x for x in metrics if x not in 
                prop_item_dict[sub_item]], key=f'prop_{counter}')
            prop_item_dict[sub_item].append(prop)
    df = pl_h2.get_data_frames_from__headers([s_header_pure], 
        df_complete, "header")[0]
    if sub_item:
        cached_obj = f"{filename}_{s_header}_obj"
        sess_obj = st.session_state.get(cached_obj, [])
        if sess_obj and sess_obj[1] == cached_obj:
            df = sess_obj[0]
        else:
            df = pl_h2.get_metrics_from_df(df, s_header_pure, s_header)
            helpers.set_state_key(cached_obj, value=df, change_key=cached_obj)
        
        df = pl_h2.get_df_from_sub_device(df, 'sub_device', sub_item)
    else:
        df = pl_h2.get_metrics_from_df(df, s_header_pure, s_header)
    df = pl_h2.create_metric_df(df, s_header_pure, prop)
    df = df.to_pandas().set_index('date')
    return df, prop


def build_metric_dataframes(df, prop, file, chart_field,
            collect_field, os_details=None, col=None, restart_headers=None,):
    df_part = df[[prop]].copy()
    df_part['file'] = file
    if col:
        df_displ = df_part.copy()
        df_displ = df_displ.drop(columns='file')
        df_ds = df_displ.describe()
        collect_field.append([helpers.restart_headers_v1(df_displ, os_details,
            restart_headers=restart_headers), df_ds, prop])
        chart_field.append([df_part, prop])
    return collect_field, chart_field

def display_stats_data(collect_field):
    """Data and statistics of each compared metric in a grid of up to
    cols_per_line columns, in the order of collect_field."""
    grid = st.grid(Config.cols_per_line)
    for entry in collect_field:
        header_part = entry[3] if len(entry) >= 4 else ''
        with grid.cell():
            st.markdown(f'###### data for {header_part} {entry[2]}')
            st.write(entry[0])
            st.markdown(f'###### statistics for {header_part} {entry[2]}')
            st.write(entry[1])