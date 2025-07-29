#!/usr/bin/python3

import streamlit as st
import dataframe_funcs_pl as dff
import pl_helpers2 as pl_helpers
import helpers_pl
import polars as pl
import dia_compute_pl as dia_compute
import multi_pdf as mpdf
import layout_helper_pl as lh
from config import Config
from concurrent.futures import ThreadPoolExecutor
# from wfork_streamlit_profiler import Profiler
# example with Profiler:

sar_structure = []
os_details = ""
file_chosen = ""

def show_dia_overview(username: str, sar_file_col: st.delta_generator.DeltaGenerator,
         sar_file: str, df: pl.DataFrame, os_details: str):
    # clear session state
    for item in st.session_state:
        if '_obj' in item:
            st.session_state.pop(item)
    # global os_details, file_chosen
    file_chosen = ""
    st.subheader('Overview of important metrics from SAR data')
    multi_pdf_field = []
    col1, col2, *_ = lh.create_columns(4, [0, 1, 1, 1])
    st.write("#")
    if sar_file != file_chosen:
        file_chosen = sar_file
    sar_file_name = sar_file
    sar_file = f'{Config.upload_dir}/{username}/{sar_file}'
    pdf_dir = f'{Config.upload_dir}/{username}/pdf'
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
    show_manpages = 1
    statistics = 1

    @st.fragment
    def metric_expander(initial_aliases: list, full_alias_l: list,
            count_lines: int, boxes_per_line: int, sel_field: list):
        col1, _ = st.columns([0.8, 0.2])
        col1.markdown("**Select which metrics to display**")
        h_expander = col1.expander(label='Choose SAR Metrics', expanded=True)
        with h_expander:
            fr_aliases = initial_aliases.copy()
            fr_full_alias = full_alias_l.copy()
            col5, col6 = st.columns(2)
            ph_col3 = col5.empty()
            ph_col4 = col6.empty()
            if ph_col3.checkbox('Select All', help="""Be cautious with this option. It will select all metrics
            and can lead to a large time delay since a lot of diagrams may be created"""):
                fr_aliases = fr_full_alias[:]
            elif ph_col4.checkbox('Deselect All'):
                fr_aliases = []
            st.markdown('***')
            for _ in range(count_lines):
                cols = st.columns(boxes_per_line)
                for x in range(len(cols)):
                    if len(fr_full_alias) > 0:
                        label = fr_full_alias.pop()
                        if label in fr_aliases:
                            value = True
                        else:
                            value = False
                        ph_sel = cols[x].empty()
                        selected = ph_sel.checkbox(label, value=value, key=f"{label}_{x}")
                        if selected:
                            sel_field.append(label)
        return sel_field

    sel_field = metric_expander(initial_aliases, full_alias_l, count_lines, boxes_per_line, sel_field)

    # pdfs,  pick time frame, diagram style
    @st.fragment
    def change_time_and_dia(df, headers):
        lh.make_vspace(4, st)
        st.markdown("**Change Start/End Time and Diagram Properties and handle PDF creation**")
        col1, _ = st.columns([0.8, 0.2])
        this_container = col1.container(border=True)
        this_container.markdown("###### Enable PDF Creation")
        df_len = 0
        tmp_dict = {}
        col1, col2, col3 = this_container.columns([0.2, 0.2, 0.6])
        lh.make_vspace(6,col1)
        lh.make_vspace(6,col2)
        lh.make_vspace(6,col3)
        create_multi_pdf = 0
        if col1.toggle('Modern Style', help='Choose between modern and classic style',
                on_change=st.rerun, args=(), kwargs={"scope": "fragment"}):
            d_style = 'modern'
        else:
            d_style = 'classic'
        if col2.toggle("Create PDF's", help="Enable or disable PDF creation"):
            enable_pdf = 1
            if col3.toggle('Create PDF from all diagrams', help='Create a PDF from all diagrams'):
                create_multi_pdf = 1
            else:
                create_multi_pdf = 0
        else:
            enable_pdf = 0
        lh.make_vspace(6,col1)
        lh.make_vspace(6,col2)
        lh.make_vspace(6,col3)
        col1.markdown("###### Set time frame")
        col2.markdown("###### ")
        lh.make_vspace(6,col1)
        lh.make_vspace(6,col2)
        lh.make_vspace(6,col3)
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
                start = start_box.selectbox('Choose Start Time', hours, index=0,)
                time_len = len(hours) - hours.index(start) -1
                end = end_box.selectbox('Choose End Time',hours[hours.index(start):],
                    index=time_len)
            break
        lh.make_vspace(6,col1)
        lh.make_vspace(6,col2)
        lh.make_vspace(6,col2)
        col1.markdown("###### Customize Diagrams")
        lh.make_vspace(4,col1)
        lh.make_vspace(4,col2)
        width, height = helpers_pl.diagram_expander('Diagram Width',
            'Diagram Height', col1)
        font_size = helpers_pl.font_expander(12, "Change Axis Font Size", "font size", col2)
        return d_style, enable_pdf, create_multi_pdf, start, end, width, height, font_size

    if sel_field:
        d_style, enable_pdf, create_multi_pdf, start, end, width, height, font_size = change_time_and_dia(df, headers)

    col1, col2, *_ = st.columns([0.1, 0.1, 0.8])
    submitted = col1.button('Show Diagrams')
    if col2.button('Clear'):
        st.rerun()
    lh.make_vspace(1, st)
    if sel_field:
        col1, _ = st.columns([0.8, 0.2])
        if submitted:
            with col1.container(border=True):
                sorted_df_dict = {}
                st_collect_list_pandas = st.session_state.get(
                    f"{sar_file_name}_collect_list_pandas", []
                )
                collect_list = st.session_state.get(f"{sar_file_name}_st_collect_list", [])
                def collect_results(result):
                    collect_list.append(result)
                title_list = [x[0]['title'] for x in collect_list] if st_collect_list_pandas else []
                with st.spinner(text='Please be patient until all graphs are constructed ...', show_time=True):
                    headers_trdict = helpers_pl.translate_aliases(sel_field, headers)
                    header_difference = [x for x in sel_field if x not in title_list]
                    remove_list = [x for x in title_list if x not in sel_field]
                    remove_set = set(remove_list)
                    new_headers_trdict = {key: headers_trdict[key] for key in header_difference if key in headers_trdict}
                    header_list = list(new_headers_trdict.values())
                    df_list = pl_helpers.get_data_frames_from__headers(header_list, df,
                        "header") 
                    for df in df_list:
                        df_result = dia_compute.prepare_df_for_pandas(df, start, end)
                        st_collect_list_pandas.append(df_result)
                    collect_list_pandas = [
                        item
                        for item in st_collect_list_pandas
                        if item[0]["title"] not in remove_set
                    ]
                    collect_list_titles = [item[0]['title'] for index, item in enumerate(collect_list)] if collect_list else []
                    with ThreadPoolExecutor() as executor:
                        futures = []
                        for outer_index in collect_list_pandas:
                            for inner_index in outer_index:
                                df = inner_index['df']
                                header = inner_index['title']
                                sub_title = inner_index['sub_title']
                                device_num = inner_index['device_num']
                                if header not in collect_list_titles: 
                                    futures.append(executor.submit(dia_compute.final_results, df, header, statistics, os_details, 
                                        restart_headers, font_size, width, height, show_manpages, device_num, sub_title,))
                        for future in futures:
                            collect_results(future.result())
                    filtered_collect_list = [x for x in collect_list if x[0]['title'] not in remove_set]
                    counter = 0
                    for item in filtered_collect_list:
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
                            tab1, tab2, tab3, tab4 = st.tabs(["📈 Chart", "🗃 Data", " 📔 man pages", " 📊 PDF", ])
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
                                    helpers_pl.metric_popover(metrics)
                            with tab4:
                                if enable_pdf:
                                    pdf_name = f'{pdf_dir}/{sar_file_name}_{header.replace(" ", "_")}.pdf'
                                    if create_multi_pdf:
                                        multi_pdf_field.append(pdf_name)
                                    helpers_pl.pdf_download(pdf_name, chart)

                                    download_name = f"{sar_file_name}_{helpers_pl.validate_convert_names(title)}.pdf"
                                    # lh.pdf_download(pdf_name, chart, download_name=download_name, key=key)
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
                                # if show_diagrams:
                                tab1, tab2, tab3, tab4 = st.tabs(["📈 Chart", "🗃 Data", " 📔 man page",
                                        " 📊 PDF",])
                                with tab1:
                                    st.altair_chart(chart, theme=None)
                                with tab2:
                                    if statistics:
                                        col1, col2, col3, col4 = lh.create_columns(
                                            4, [0, 0, 1, 1])
                                        col1.markdown(f'###### Sar Data for {title if not sub_title else sub_title}')
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
                                        helpers_pl.metric_popover(metrics)
                                with tab4:
                                    if enable_pdf:
                                        pdf_name = f'{pdf_dir}/{sar_file_name}_{sub_title.replace(" ", "_")}.pdf'
                                        if create_multi_pdf:
                                            multi_pdf_field.append(pdf_name)
                                        helpers_pl.pdf_download(pdf_name, chart)
                                        # download_name = f"{sar_file_name}_{helpers_pl.validate_convert_names(title)}.pdf"
                                        # lh.pdf_download(pdf_name, chart, download_name=download_name, key=f"{key}_{subitem}")
                                    else:
                                        st.write("You have to enable the PDF checkbox on the top. It is disabled\
                                                 by default because the current implementation is quite performance intensive")

                                counter +=1
                        # st.markdown("___")
                    st.session_state[f'{sar_file_name}_collect_list_pandas'] = collect_list_pandas
                    st.session_state[f'{sar_file_name}_st_collect_list'] = collect_list
                    # cleanup old session state keys
                    session_collect_keys = [key for key in st.session_state.keys() if 'collect_list' in key]
                    for key in session_collect_keys:
                        if sar_file_name not in key:
                            st.session_state.pop(key)
                    if create_multi_pdf:
                        download_name = f"{sar_file_name}_diagrams.pdf"
                        pdf_file = f"{pdf_dir}/{download_name}"
                        outfile = mpdf.create_multi_pdf(multi_pdf_field, pdf_file)
                        helpers_pl.multi_pdf_download(outfile)
                    st.markdown("___")
                if st.button('Back to top'):
                    st.rerun()
