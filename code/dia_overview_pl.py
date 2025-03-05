#!/usr/bin/python3

import streamlit as st
import multiprocess as multiprocessing
import dataframe_funcs_pl as dff
import pl_helpers2 as pl_helpers
import parse_into_polars as parse_polars
import helpers_pl
import dia_compute_pl as dia_compute
import multi_pdf as mpdf
import layout_helper_pl as lh
from config import Config

sar_structure = []
os_details = ""
file_chosen = ""
def show_dia_overview(username: str, sar_file_col: st.delta_generator.DeltaGenerator):
    # clear session state
    for item in st.session_state:
        if '_obj' in item:
            st.session_state.pop(item)

    collect_list = []
    collect_list_pandas = []
    #global os_details, file_chosen
    file_chosen = ""
    sar_file = helpers_pl.get_sar_files(username, col=sar_file_col, key="dia_overview")
    st.subheader('Overview of important metrics from SAR data')
    col1, col2, col3, col4 = lh.create_columns(4, [0.7, 0.1, 0.4, 0.4])
    op_ph2 = col2.empty()
    op_ph3 = col3.empty()
    op_ph4 = col4.empty()
    dia_style = col2.empty()
    multi_pdf = col4.empty()
    pdf_check = col3.empty()
    multi_pdf_field = []
    create_multi_pdf = 0
    col1, col2, col3, col4 = lh.create_columns(4, [0, 1, 1, 1])
    st.write("#")
    if sar_file != file_chosen:
        file_chosen = sar_file

    sar_file_name = sar_file
    sar_file = f'{Config.upload_dir}/{username}/{sar_file}'
    df =parse_polars.get_data_frame(sar_file, username)
    os_details = pl_helpers.get_os_details_from_df(df)
    pdf_dir = f'{Config.upload_dir}/{username}/pdf'
    sar_file_col.text(f"Operating System Details: {os_details}")
    headers = pl_helpers.get_headers(df)
    restart_headers = pl_helpers.get_restart_headers(df)

    initial_aliases = ['CPU', 'Kernel tables', 'Load', 'Memory utilization',
    'Swap utilization']

    full_alias_d = helpers_pl.translate_headers(headers)

    full_alias_l = list(full_alias_d.values())
    full_alias_l.sort(reverse=True)
    sel_field = []

    length =  len(headers)
    boxes_per_line = 5
    count_lines = length / boxes_per_line
    if count_lines > 0:
        count_lines = int(count_lines + 1)
  
    op_ph2.markdown("**Choose between diagram styles**")
    if dia_style.checkbox('Modern Style'):
        d_style = 'modern'
    else:
        d_style = 'classic'
    op_ph3.markdown("**Choose if you need to save your diagrams as PDF**")
    if pdf_check.checkbox('Enable PDF saving'):
        enable_pdf = 1
        op_ph4.markdown('**Create Summary PDF from all selected diagrams**')
        if multi_pdf.checkbox('Create PDF'):
            create_multi_pdf = 1
    else:
        enable_pdf = 0
    show_manpages = 1
    statistics = 1

    def collect_results(result):
        collect_list.append(result)
    
    col1, col2, col3, col4 = lh.create_columns(4, [0, 0, 1, 1])
    st.markdown("**Select which metrics to display**")
    h_expander = st.expander(label='Choose SAR Metrics',expanded=False)
    with h_expander:
        col5, col6 = st.columns(2)
        ph_col3 = col5.empty()
        ph_col4 = col6.empty()
        if ph_col3.checkbox('Select All'):
            initial_aliases = full_alias_l[:]
        elif ph_col4.checkbox('Deselect All'):
            initial_aliases = []
        st.markdown('***')
        for _ in range(count_lines):
            cols = st.columns(boxes_per_line)
            for x in range(len(cols)):
                if len(full_alias_l) > 0:
                    label = full_alias_l.pop()
                    if label in initial_aliases:
                        value = True
                    else:
                        value = False

                    ph_sel = cols[x].empty()
                    selected = ph_sel.checkbox(label, value=value, key=f"{label}_{x}")
                    if selected:
                        sel_field.append(label)

    # pick time frame
    st.markdown("**Change Start/End Time**")
    time_expander = st.expander(label='Choose Time',expanded=False)
    with time_expander:
        df_len = 0
        tmp_dict = {}
        col1, col2, col3, col4 = lh.create_columns(4, [0, 0, 1, 1])
        for entry in headers:
            # findout longest hour range if in rare cases it
            # differs since a new device occured after reboot (persistent
            # rules network device)
            date_df = pl_helpers.get_data_frames_from_header([entry], df)
            date_df = date_df.sort('date').unique('date')
            hours = dff.translate_dates_into_list(date_df)
            if not hours:
                continue
            if len(hours) >= df_len:
                tmp_dict[df_len] = entry
                df_len = len(hours)
            if date_df is not None:
                start_box = col1.empty()
                end_box = col2.empty()
                hours = dff.translate_dates_into_list(date_df)
                start = start_box.selectbox('Choose Start Time', hours, index=0)
                time_len = len(hours) - hours.index(start) -1
                end = end_box.selectbox('Choose End Time',hours[hours.index(start):],
                    index=time_len)
            break
        
    with st.form(key='main_section'):
        st.markdown("**Customize Diagrams**")
        cols = st.columns(8)
        width, height = helpers_pl.diagram_expander('Diagram Width',
            'Diagram Hight', cols[0])
        font_size = helpers_pl.font_expander(12, "Change Axis Font Size", "font size", cols[1])

        if st.checkbox('Show diagrams on submit', value=True):
            show_diagrams = 1
        else:
            show_diagrams = 0
        submitted = st.form_submit_button('Submit')
        st.markdown("___")
        if submitted:
            sorted_df_dict = {}
            with st.spinner(text='Please be patient until all graphs are constructed ...', show_time=True):
                headers_trdict = helpers_pl.translate_aliases(sel_field, headers)
                header_list = list(headers_trdict.values())
                df_list = pl_helpers.get_data_frames_from__headers(header_list, df,
                    "header") 
                for df in df_list:
                    df_result = dia_compute.prepare_df_for_pandas(df, start, end)
                    collect_list_pandas.append(df_result)
                
                # collect all results from multiprocessing and pandas df
                # polars df is not supported by multiprocessing('fork')
                pool = multiprocessing.Pool()
                for outer_index in collect_list_pandas:
                    for inner_index in outer_index:
                        df = inner_index['df']
                        header = inner_index['title']
                        sub_title = inner_index['sub_title']
                        device_num = inner_index['device_num']
                        pool.apply_async(dia_compute.final_results, args=(df, header, statistics,
                            os_details, restart_headers, font_size, width, height, 
                                show_manpages, device_num, sub_title), callback=collect_results)
                pool.close()
                pool.join()
                counter = 0
                for item in collect_list:
                    header = item[0]['header']
                    title = item[0]['title']
                    if not sorted_df_dict.get(header):
                        sorted_df_dict[header] = []
                        sorted_df_dict[header].append(item)
                    else:
                        sorted_df_dict[header].append(item)
                for key in sorted_df_dict.keys():
                    # no sub_devices
                    if len(sorted_df_dict[key]) == 1:
                        header = sorted_df_dict[key][0][0]['header']
                        chart = sorted_df_dict[key][0][0]['chart']
                        device_num = sorted_df_dict[key][0][0]['device_num']
                        sub_title = sorted_df_dict[key][0][0]['sub_title']
                        dup_bool = sorted_df_dict[key][0][0]['dup_bool']
                        dup_check = sorted_df_dict[key][0][0]['dup_check']
                        df_describe = sorted_df_dict[key][0][0]['df_describe']
                        df_stat  = sorted_df_dict[key][0][0]['df_stat']
                        metrics = sorted_df_dict[key][0][0]['metrics']
                        st.markdown(f'#### {header}')
                        if show_diagrams:
                            tab1, tab2, tab3, tab4 = st.tabs(["📈 Chart", "🗃 Data", " 📔 man page", " 📊 PDF", ])
                        else:
                            _, tab1, tab2, tab3, tab4 = st.tabs(["✌️", "📈 Chart", "🗃 Data", " 📔 man page", " 📊 PDF", ])
                        with tab1:
                            if sub_title == 'all':
                                st.markdown(f'###### all of {device_num}')
                            if d_style == 'modern':
                               st.altair_chart(chart, use_container_width=True, )
                            else:
                                st.altair_chart(chart, use_container_width=True, theme=None)
                        with tab2:
                            if statistics:
                                col1, col2, col3, col4 = lh.create_columns(
                                    4, [0, 0, 1, 1])
                                
                                col1.markdown(f'###### Sar Data for {header}')
                                st.write(df_stat)
                                if dup_bool:
                                   col1.warning('Be aware that your data contains multiple indexes')
                                   col1.write('Multi index table:')
                                   col1.write(dup_check)
                                st.markdown(f'###### Statistics for {header}')
                                st.write(df_describe)
                        with tab3:
                            if show_manpages:
                                for metric in metrics:
                                    helpers_pl.metric_expander(metric)
                        with tab4:
                            if enable_pdf:
                                pdf_name = f'{pdf_dir}/{sar_file_name}_{header.replace(" ", "_")}.pdf'
                                if create_multi_pdf:
                                    multi_pdf_field.append(pdf_name)
                                helpers_pl.pdf_download(pdf_name, chart)
                            else:
                                st.write("You have to enable the PDF checkbox on the top. It is disabled\
                                         by default because the current implementation is quite performance intensive")

                        counter += 1
                    else:
                        # sub_devices
                        header = sorted_df_dict[key][0][0]['header']
                        st.markdown(f'#### {header}')
                        counter = 0
                        for subitem in sorted_df_dict[key]:
                            subitem_dict = subitem[0]
                            chart = subitem_dict['chart']
                            dup_bool = subitem_dict['dup_bool']
                            dup_check = subitem_dict['dup_check']
                            df_describe = subitem_dict['df_describe']
                            df_stat  = subitem_dict['df_stat']
                            title = subitem_dict['title']
                            sub_title = subitem_dict['sub_title']
                            if show_diagrams:
                                tab1, tab2, tab3, tab4 = st.tabs(["📈 Chart", "🗃 Data", " 📔 man page",
                                    " 📊 PDF",])
                            else:
                                _, tab1, tab2, tab3, tab4 = st.tabs(["✌️", "📈 Chart",
                                    "🗃 Data", " 📔 man page", " 📊 PDF",])
                            with tab1:
                                st.altair_chart(chart, theme=None)
                            with tab2:
                                if statistics:
                                    col1, col2, col3, col4 = lh.create_columns(
                                        4, [0, 0, 1, 1])
                                    if not sub_title:
                                        col1.markdown(f'###### Sar Data for {title}')
                                    else:
                                        col1.markdown(f'###### Sar Data for {sub_title}')
                                    st.write(df_stat)
                                    if dup_bool:
                                       col1.warning(
                                           'Be aware that your data contains multiple indexes')
                                       col1.write('Multi index table:')
                                       col1.write(dup_check)
                                    if not sub_title:
                                        st.markdown(f'###### Statistics for {title}')
                                    else:
                                        st.markdown(f'###### Statistics for {sub_title}')
                                    st.write(df_describe)
                            with tab3:
                                if show_manpages:
                                    metrics =  subitem_dict['metrics']
                                    for metric in metrics:
                                        helpers_pl.metric_expander(metric)
                            with tab4:
                                if enable_pdf:
                                    pdf_name = f'{pdf_dir}/{sar_file_name}_{sub_title.replace(" ", "_")}.pdf'
                                    if create_multi_pdf:
                                        multi_pdf_field.append(pdf_name)
                                    helpers_pl.pdf_download(pdf_name, chart)
                                else:
                                    st.write("You have to enable the PDF checkbox on the top. It is disabled\
                                             by default because the current implementation is quite performance intensive")

                            counter +=1
                    st.markdown("___")
                if create_multi_pdf:
                    download_name = f"{sar_file_name}_diagrams.pdf"
                    pdf_file = f"{pdf_dir}/{download_name}"
                    outfile = mpdf.create_multi_pdf(multi_pdf_field, pdf_file)
                    helpers_pl.multi_pdf_download(outfile)
                st.markdown("___")

            if st.form_submit_button('Back to top'):
                st.experimental_rerun()
