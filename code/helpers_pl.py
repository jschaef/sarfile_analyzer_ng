#!/usr/bin/python3

import os
import streamlit as st
import pandas as pd
import time
import re
import download as dow
import dataframe_funcs_pl as dff
import layout_helper_pl as lh
import sqlite2_polars
from datetime import datetime
from config import Config

reg_linux_restart = re.compile('LINUX RESTART', re.IGNORECASE)

class configuration(object):
    def __init__(self, config_d):
        self.conf_d = config_d
    def set_conf(self,key,val):
        self.conf_d[key]=val
    def get_conf(self,key):
        return self.conf_d[key]
    def update_conf(self, upd_d):
        self.conf_d.update(upd_d)
    def get_dict(self):
        return self.conf_d

def extract_os_details(file):
    with open(file, 'r') as sar_file:
        for _, line in enumerate(sar_file):
            if "Linux" in line:
                return line.split()

def merge_headers(header_field):
    # initialize with first field
    first = set(header_field[0])
    def f(x, y):
        return x.intersection(y)
    for field in header_field[1:]:
        res = f(first, field)
        first = res

    arr = sorted([x for x in first])
    if 'all' in arr:
        arr.remove('all')
        # sort numeric values
        tmp_arr = [int(x) for x in arr if str(x).isnumeric()]
        if tmp_arr:
            tmp_arr.sort()
            arr = [str(x) for x in tmp_arr]
        arr.insert(0,'all')
    return(arr)

def translate_headers(field):
    '''
    takes list of headers , db lookup for the aliases
    search for header belonging to aliases
    returns dictionary {header:alias, header:alias, ..., n}
    if header not in db, put the original header as key and value
    '''
    aliases = {}
    for header in field:
        if reg_linux_restart.search(header):
            continue
        alias = sqlite2_polars.get_header_prop(header, 'alias')
        if alias:
            aliases[header] = alias
        else:
            aliases[header] = header

    return aliases

def translate_aliases(alias_field, sar_headers):
    '''
    takes a list of aliases and returns the related headers
    as a dictionary {alias:header,...}
    '''
    headers = {}
    for alias in alias_field:
        header = sqlite2_polars.get_header_from_alias(alias)
        if not header:
            header = alias
        if header not in sar_headers: 
            header = aliases_2_header(sar_headers, header)      
        # refurbish whitespaces in db
        header = " ".join(header.split())
        headers[alias] = header
    return headers

# In case there is no alias because header differs a little bit
# from headers saved in DB
def aliases_2_header(header_field, alias_header):
    result_dict = {}
    result_header = ""
    for header in header_field:
        result_dict[header] = 0
        for metric in alias_header.split():
            if metric in header.split():
                result_dict[header] += 1 
    tmp_count = 0
    for header in result_dict.keys():
        if result_dict[header] > tmp_count:
           tmp_count = result_dict[header]
           result_header = header
    return result_header

###################################################
# Helpers regarding app organization
def get_selected_header(select_box_title, headers, col=None, key=None):
    '''
    select_box_title -> title for the selectbox
    headers -> field with headers
    '''
    # convert headers into aliases
    aliases = translate_headers(headers)
    selected_sorted = [a for a in aliases.values()]
    selected_sorted.sort()

    if not col:
        ph = st.sidebar.empty()
    else:
        ph = col.empty()

    selected = ph.selectbox(select_box_title, selected_sorted,key=key)

    
    #retransform
    for key in aliases:
        if aliases[key] == selected:
            selected = key
            break
    return (selected, ph)

@st.cache_resource
def get_metric_desc_from_manpage():
    metric_reg = re.compile(r'^\.IP\s+(.*$)')
    content = re.compile(r'^[^\.].*$')

    with open('sar.1', 'r') as mfile:
        mh_dict = {}
        m_hit = 0
        metric = ''
        linefield = mfile.readlines()

        for line in linefield[129:]:
            if metric_reg.search(line):
                hit = metric_reg.match(line)
                metric = hit.group(1)
                if metric:
                    mh_dict[metric] = []
                    m_hit = 1
            elif m_hit == 1 and content.search(line):
                mh_dict[metric].append(line)
            elif not content.search(line):
                m_hit= 0

    for metric in mh_dict.keys():
        yield (metric, " ".join(mh_dict[metric]).rstrip())

def metric_expander(prop, expand=False, col=None):
    col = col if col else st
    col1 = col.columns([1, 1])[0]
    description = sqlite2_polars.ret_metric_description(prop)
    exp_desc = f"{prop}"
    ph_expander = col1.empty()
    my_expander = ph_expander.expander(
        exp_desc, expanded=expand)
    with my_expander:
        if description:
            col.write(description)
        else:
            col.write(f'metric {prop} has no description at the moment')

def metric_popover(prop_list, col=None, key=None):
    col = col if col else st
    number_cols = len(prop_list)
    cols = col.columns(number_cols)
    for index, prop in enumerate(prop_list):
        description = sqlite2_polars.ret_metric_description(prop)
        col = cols[index]
        with col.popover(f'{prop}',disabled=False):
            if description:
                st.text(description)
            else:
                st.text(f'metric {prop} has no description at the moment')
    st.markdown("######")

def measure_time(col: st.delta_generator.DeltaGenerator, prop: str = 'start', start_time: float = None):
    if prop == 'start':
        start_time = time.perf_counter()
        return start_time
    else:
        end = time.perf_counter()
        col.write(f'process_time: {round(end-start_time, 4)}')

def get_sar_files(user_name: str, col: st.delta_generator.DeltaGenerator=None, key: str=None):
    sar_files = [x for x in os.listdir(f'{Config.upload_dir}/{user_name}') \
        if os.path.isfile(f'{Config.upload_dir}/{user_name}/{x}') ]
    sar_files_pre = [x for x in sar_files if not x.endswith('.parquet') ]
    sar_files = [x.replace(".parquet", "") for x in sar_files if x.endswith('.parquet')]
    sar_files.extend(sar_files_pre)
    lh.make_vspace(1, col)
    if not col:
        col1, col2, col3 = st.columns([2,1, 1])
        col1.write(''), col3.write('')
        selection = col2.selectbox('**Choose your Sar File**', sar_files, key=key)
    else:
        selection = col.selectbox('**Choose your Sar File**', sar_files, key=key)
    return selection

def diagram_expander(text1, text2, col=None, key=None):
    col = col if col else st
    dia_expander = col.expander('Change Diagram Size')
    st.markdown('')
    with dia_expander:
        width = st.slider(text1,
            400, 1600, (1200), 200, key=f"{key}_w")
        hight = st.slider(text2,
            400, 1600, (400), 200, key=f"{key}_h")

        return width, hight

def font_expander(default_size, title, description, col=None, key=None):
    col = col if col else st
    font_expander = col.expander(title)
    st.markdown('')
    with font_expander:
        size = st.select_slider(description,
                          range(8,25), value=default_size, key=key)

        return size

def rename_sar_file(file_path, col=None):
    col = col if col else st
    os_details = extract_os_details(file_path)
    hostname = os_details[2].strip("(|)")
    date = os_details[3]
    date = date.replace('/','-')
    today = datetime.today().strftime("%Y-%m-%d")
    base_name = os.path.basename(file_path)
    dir_name = os.path.dirname(file_path)
    rename_name = f'{today}_{hostname}_{date}'
    renamed_name = f'{dir_name}/{rename_name}'
    try:
        os.system(f'mv {file_path} {dir_name}/{rename_name}')
        col.info(fr'{base_name} has been renamed to {rename_name}\n    \
            which means: <date_of_upload>\_<hostname>\_<sar file creation date>')
        return rename_name
    except Exception as e:
        col.warning(f'file {file_path} could not be renamed to {renamed_name}')
        col.warning(f'exception is {e}')

def pdf_download(file, dia):
    my_file = file
    save_dir = os.path.dirname(file)
    if not os.path.exists(save_dir):
        os.system(f'mkdir -p {save_dir}')
    if not os.path.exists(my_file):
        dia.save(my_file)
    filename = file.split('/')[-1]
    with open(my_file, 'rb') as f:
        s = f.read()
    download_button_str = dow.download_button(
        s, filename, 'Click here to download PDF')
    st.markdown(download_button_str, unsafe_allow_html=True)

def multi_pdf_download(file):
    filename = file.split('/')[-1]
    with open(file, 'rb') as f:
        s = f.read()
    download_button_str = dow.download_button(
        s, filename, 'Click here to download the multi PDF')
    st.markdown(download_button_str, unsafe_allow_html=True)

def set_stile(df, restart_rows=None):
    # left as example
    #def color_null_bg(val):
    #    is_null = val == 0
    #    return ['background-color: "",' if v else '' for v in is_null]
    
    def color_null_fg(val):
        is_null = val == 0
        return ['color: "",' if v else '' for v in is_null]

    if restart_rows:
        multi_index = [ x.index[0] for x in restart_rows ]
    else:
        multi_index = []
    sub_index = [ x for x in df.index if x not in multi_index ]
    df = df.style.apply(highlight_ind, dim='min',
        subset=pd.IndexSlice[sub_index, :]).apply(highlight_ind,
         subset=pd.IndexSlice[sub_index,:]).\
         apply(highlight_min_ind, subset=pd.IndexSlice[sub_index, :]).\
        apply(highlight_max_ind, subset=pd.IndexSlice[sub_index, :]).\
        format(precision=4)
    if restart_rows:
        df = df.apply(color_restart, subset=pd.IndexSlice[multi_index, :])
   
    return(df)

def highlight_ind(data,  dim='max', color='black'):
    '''
    highlight the maximum in a Series or DataFrame
    '''
    attr = f'color: {color}'
    if data.ndim == 1:

        if dim == 'max':
            quant = data == data.max()

        elif dim == 'min':
            quant = data == data.min()
        
        return [attr if v else '' for v in quant]


def highlight_max_ind(data, color='lightblue'):
    '''
    highlight the maximum in a Series yellow.
    '''
    is_max = data == data.max()
    return [f'background-color: {color}' if v else '' for v in is_max]


def highlight_min_ind(data, color='yellow'):
    '''
    highlight the minimum in a Series yellow.
    '''
    is_min = data == data.min()

    return [f'background-color: {color}' if v else '' for v in is_min]

def color_restart(data):
    result = data == 0.00
    return ['color: red'  for v in result]

def extract_restart_header(headers):
    return [header for header in headers if reg_linux_restart.search(
        header) ]

def restart_headers(df, os_details, restart_headers=None, display=True, 
        col: st.delta_generator.DeltaGenerator=None):
    # check and remove duplicates
    if not col:
        col = st
    dup_check = df[df.index.duplicated()]
    if not dup_check.empty:
        df = df[~df.index.duplicated(keep='first')].copy()
    if restart_headers:
        rdf = df.copy()
        rdf, new_rows = dff.insert_restarts_into_df(os_details, rdf,
            restart_headers)
        if display:
            col.write(set_stile(rdf, restart_rows=new_rows))
            code1 = '''max:\tlightblue\nmin:\tyellow'''
            code2 = f'''\nreboot:\t{" ,".join([restart.split()[-1] for restart in restart_headers])}'''
            col.code(code1 + code2)
        else:
            return(set_stile(rdf, restart_rows=new_rows))
    else:
        if display:
            col.write(set_stile(df))
            code2 = ""
            code1 = '''max:\tlightblue\nmin:\tyellow'''
            col.code(code1 + code2)
            col.text('')
            col.text('')
        else:
            return(set_stile(df))


def restart_headers_v1(df, os_details, restart_headers=None):
    if restart_headers:
        rdf = df.copy()
        rdf, new_rows = dff.insert_restarts_into_df(os_details, rdf,
                      restart_headers)
        return set_stile(rdf, restart_rows=new_rows)
    else:
        return set_stile(df)

def get_start_end_date(date_list: list, point: str="start") -> datetime:
    """compares pd.dateTime objects and returns either the min or the max val 

    Args:
        date_list (list): _description_
        point (str, optional): _description_. Defaults to "start".

    Returns:
        pd.datetime: _description_
    """
    pd_index = pd.DatetimeIndex(date_list)
    return pd_index.max() if point == "end" else pd_index.min()

def get_df_from_start_end(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    start, end = dff.replace_ymt(start, end, df)
    start_index = pd.Timestamp.now()
    end_index = pd.Timestamp.now()
    for x_start in range(len(df.index)):
        if df.index[x_start] >=start:
            start_index = df.index[x_start]
            break
    for x_end in range(len(df.index)-1,-1,-1):
        if df.index[x_end] <=end:
            end_index = df.index[x_end]
            break
    return df[start_index:end_index]

def create_start_end_time_list(start: pd.DatetimeIndex, end: pd.DatetimeIndex, col1: object, col2: object):
    if not start or not end:
        return None, None
    start_d = start.replace(microsecond=0, second=0, minute=0)
    end_d = end.replace(microsecond=0, second=0, minute=0, hour=end.hour)
    x = pd.date_range(start_d, end_d, freq='h')
    x = x.delete(0).insert(0,start).append(pd.date_range(pd.Timestamp(end), periods=1))
    y_start = pd.DataFrame(x.strftime('%H:%M:%S'), index=x)
    y_start.columns = ['time']
    start_key = "time_start"
    start_time = col1.selectbox('Start', y_start['time'], key=start_key)
    tmp_x = x.to_series(index=range(len(x)))
    for index in range(len(tmp_x)):
        if tmp_x[index] >= y_start.index[y_start['time'] == start_time][0]:
            start_time = tmp_x[index]
            break
    end_choice = x[index+1:]
    date_time_col = end_choice.to_pydatetime()
    end_key = "time_end"
    time_end_choice = pd.DataFrame(end_choice.strftime('%H:%M:%S'), index=end_choice)
    time_end_time  = col2.selectbox('End', time_end_choice, index=len(end_choice)-1, key=end_key)
    time_end_choice[1] = date_time_col
    end_time = time_end_choice[time_end_choice[0]==time_end_time][1].iloc[0]
    return start_time, end_time

def clean_session_state(*args):
    for entry in args:
        st.session_state.pop(entry, None)

def set_state_key(sess_key, value=None, change_key=None):
    if sess_key in st.session_state and st.session_state[sess_key][1] == change_key:
        return st.session_state[sess_key][0]
    else:
        st.session_state[sess_key] = [value, change_key]
        return st.session_state[sess_key][0]

def validate_convert_names(subject: str)-> str:
    subject = subject.replace(" ", "_").replace('%',"percent_").replace('/s',"_per_second_").replace('_-',"-")
    return subject

if __name__ == '__main__':
    pass
