#!/usr/bin/python3
import streamlit as st
import os
import single_file_pl
import multi_files_pl
import dia_overview_pl
import handle_metrics_pl
import helpers_pl as helpers
import display_multi
import layout_helper_pl as lh
import helpers_pl
import parse_into_polars as parse_polars
import pl_helpers2 as pl_helpers

def analyze(config_c: helpers.configuration, username: str):
    config = config_c.get_dict()
    upload_dir = config ['upload_dir']
    lh.make_vspace(1, st)
    col1, _, col3, col4, _  = st.columns([1,0.2, 0.8, 1.2, 1],gap="medium")
    ph1 = col1.empty()
    ph3 = col3.empty()
    ph4 = col4.empty()
    ph41 = col4.empty()
    # present existing files, default latest uploaded
    # TODO do sanity checks for size or number of files
    sar_files = os.listdir(upload_dir)
    # exclude pickle files
    with ph1:
        lh.make_vspace(1, ph1)
        single_multi = st.selectbox('**Analyze/Compare**', ['Graphical Overview',
         'Detailed Metrics View', 'Multiple Sar Files', 
         'Metrics on many devices', 'Compare Metrics'])

    sar_file = helpers_pl.get_sar_files(username, col=ph3, key="get_sarfiles")
    sar_file_parm = sar_file
    sar_file = f"{upload_dir}/{sar_file}"
    df =parse_polars.get_data_frame(sar_file, username)
    os_details = pl_helpers.get_os_details_from_df(df)
    with ph4:
        lh.make_vspace(6, ph4)
        #ph4.markdown("**Operating System Details:**")
        ph4.markdown("**Operating System Details:**")
        ph41.write(os_details)

    st.markdown('___')

    files_exists = 0
    for entry in sar_files:
        if os.path.isfile(f"{upload_dir}/{entry}"):
            files_exists = 1
            break
    if not len(sar_files) or not files_exists:
        st.write('')
        st.warning('Nothing to analyze at the moment. You currently have no sar file uploaded.\n\
                   Upload a file in the "Manage Sar Files" menu on the top bar')
    else:
        if single_multi == 'Graphical Overview':
            dia_overview_pl.show_dia_overview(username, ph4, sar_file_parm, df, os_details)

        elif single_multi == 'Detailed Metrics View':
            single_file_pl.single_f(config, username, sar_file_parm, df, os_details)

        elif single_multi == 'Multiple Sar Files':
            multi_files_pl.single_multi(config, username, [ph3, ph4, ph41])

        elif single_multi == 'Compare Metrics':
            handle_metrics_pl.do_metrics(config, username, sar_file_parm, df, os_details) 
        elif single_multi == 'Metrics on many devices':
            display_multi.show_multi(config, username, sar_file_parm, df, os_details)
