#!/usr/bin/python3
import streamlit as st
import os
import single_file_pl
import multi_files_pl
import dia_overview_pl
import handle_metrics_pl
import helpers_pl as helpers

def analyze(config_c: helpers.configuration, username: str):
    config = config_c.get_dict()
    upload_dir = config ['upload_dir']
    col1, _, col3, _ = st.columns([1,2, 1, 1])
    #present existing files, default latest uploaded
    #TODO do sanity checks for size or number of files
    sar_files = os.listdir(upload_dir)
    # exclude pickle files
    with col1:
        single_multi = st.selectbox('Analyze/Compare', ['Graphical Overview',
         'Detailed Metrics View', 'Multiple Sar Files', 'Compare Metrics'])

    col1, _ = st.columns([0.3,0.7])
    col1.markdown('___')

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
            dia_overview_pl.show_dia_overview(username, col3)

        elif single_multi == 'Detailed Metrics View':
            single_file_pl.single_f(config, username)

        elif single_multi == 'Multiple Sar Files':
            multi_files_pl.single_multi(config, username)

        elif single_multi == 'Compare Metrics':
            handle_metrics_pl.do_metrics(config, username) 