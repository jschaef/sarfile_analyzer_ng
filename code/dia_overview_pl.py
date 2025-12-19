#!/usr/bin/python3

import streamlit as st
import dataframe_funcs_pl as dff
import pl_helpers2 as pl_helpers
import helpers_pl
import polars as pl
import dia_compute_pl as dia_compute
import multi_pdf as mpdf
import layout_helper_pl as lh
import bokeh_charts
from config import Config
from concurrent.futures import ThreadPoolExecutor
import gc
# from wfork_streamlit_profiler import Profiler
# example with Profiler:

sar_structure = []
os_details = ""
file_chosen = ""

def cleanup_chart_memory():
    """Force garbage collection and clear chart-related session state"""
    # Remove chart data from session state
    keys_to_remove = [key for key in st.session_state.keys() 
                      if any(x in key for x in ['_obj', '_chart', 'collect_list', '_pdf'])]
    for key in keys_to_remove:
        st.session_state.pop(key, None)
    
    # Force garbage collection to free memory
    gc.collect()

def show_dia_overview(username: str, sar_file_col: st.delta_generator.DeltaGenerator,
         sar_file: str, df: pl.DataFrame, os_details: str):
    # Clear session state and free memory
    cleanup_chart_memory()
    # global os_details, file_chosen
    file_chosen = ""
    st.subheader('Overview of important metrics from SAR data')
    
    multi_pdf_chart_field = []
    col1, col2, *_ = lh.create_columns(4, [0, 1, 1, 1])
    st.write("#")
    if sar_file != file_chosen:
        file_chosen = sar_file
    sar_file_name = sar_file
    sar_file = f'{Config.upload_dir}/{username}/{sar_file}'
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
                        selected = ph_sel.checkbox(label, value=value)
                        if selected:
                            sel_field.append(label)
        return sel_field

    sel_field = metric_expander(initial_aliases, full_alias_l, count_lines, boxes_per_line, sel_field)

    # pdfs,  pick time frame, diagram style
    @st.fragment
    def change_time_and_dia(df, headers):
        st.space()
        st.markdown("**Change Start/End Time and Diagram Properties and handle PDF creation**")
        col1, _ = st.columns([0.8, 0.2])
        this_container = col1.container(border=True)
        df_len = 0
        tmp_dict = {}
        col1, col2, col3 = this_container.columns([0.2, 0.2, 0.6])
        for coumn in col1, col2, col3:
            coumn.space()
        create_multi_pdf = 0
        col1.space('small'), col2.space(), col3.space()
        if col1.toggle('Create PDF from all diagrams', help='Create a PDF from all diagrams'):
            create_multi_pdf = 1
        else:
                create_multi_pdf = 0
        for coumn in col1, col2, col3:
            coumn.space()
        col1.markdown("##### Set time frame")
        col2.space()

        for column in  col2, col3:
            column.space("medium")
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
        for coumn in col1, col2:
            coumn.space()
        col1.markdown("##### Customize Diagrams")
        col2.markdown("##### ")
        col1.space(), col2.space()
        width, height = helpers_pl.diagram_expander('Diagram Width',
            'Diagram Height', col1)
        font_size = helpers_pl.font_expander(12, "Change Axis Font Size", "font size", col2)
        return create_multi_pdf, start, end, width, height, font_size

    if sel_field:
        create_multi_pdf, start, end, width, height, font_size = change_time_and_dia(df, headers)

    col1, col2, *_ = st.columns([0.1, 0.1, 0.8])
    st.markdown('<div id="show-diagrams-section"></div>', unsafe_allow_html=True)
    submitted = col1.button('Show Diagrams')
    if col2.button('Clear'):
        st.rerun()
    lh.make_vspace(1, st)
    
    # Check data size and warn user about memory implications
    # Calculate actual DataFrame memory size
    if hasattr(df, 'estimated_size'):
        # Polars DataFrame
        df_size_mb = df.estimated_size() / (1024 * 1024)
    else:
        # Pandas DataFrame or fallback - estimate based on row count and columns
        df_size_mb = (len(df) * len(df.columns) * 8) / (1024 * 1024)  # Rough estimate: 8 bytes per value
    
    num_metrics_selected = len(sel_field) if sel_field else 0
    
    if df_size_mb > 50 and num_metrics_selected > 10:
        st.warning(f"""⚠️ **Large Dataset Warning**: You have selected {num_metrics_selected} metrics from a {df_size_mb:.1f}MB dataset.
        
This may consume significant browser memory (potentially 5-15 GB). 

**Browser Memory Issue**: Once browser memory goes high, it may NOT decrease even after selecting fewer metrics or refreshing the page.

**If experiencing high memory (>5GB)**:
1. **Close this browser tab completely** (Ctrl+W or right-click → Close Tab)
2. **Open a new tab** and navigate back to the app
3. This forces the browser to release all accumulated memory

**Recommendations**:
- **Reduce metrics**: Select fewer metrics (5-10 recommended for large files)
- **Limit time range**: Use the time frame selector below to analyze smaller periods
- **Use "Detailed Metrics View"**: Better for analyzing specific metrics from large files
        """)
    
    if sel_field:
        col1, _ = st.columns([0.8, 0.2])
        if submitted:
            # Hard limit on number of charts to prevent browser crash
            MAX_CHARTS = 50 if df_size_mb > 100 else 70
            
            if num_metrics_selected > MAX_CHARTS:
                st.error(f"""🛑 **Too Many Metrics Selected**: You selected {num_metrics_selected} metrics, but the limit is {MAX_CHARTS} for files of this size.
                
Please reduce your selection to {MAX_CHARTS} or fewer metrics to prevent browser memory issues.""")
                st.stop()
            
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
                            df_chart = sorted_df_dict[key][0][0]['df']
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
                                chart_html, bokeh_fig = bokeh_charts.overview_v1(
                                    df_chart,
                                    restart_headers,
                                    os_details,
                                    font_size=font_size,
                                    width=width,
                                    height=height,
                                    title=f"{header}",
                                )
                                st.components.v1.html(chart_html, height=height + 100, scrolling=True)
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
                                # Optimize: only generate individual PDFs when not creating multi-PDF
                                if create_multi_pdf:
                                    multi_pdf_chart_field.append(bokeh_fig)
                                    st.info("ℹ️ Chart will be included in the combined PDF at the bottom of the page.")
                                else:
                                    pdf_name = f'{sar_file_name}_{header.replace(" ", "_")}.pdf'
                                    lh.pdf_download_bokeh(bokeh_fig, pdf_name, key=pdf_name)

                            counter += 1
                        else:
                            # sub_devices
                            header = sorted_df_dict[key][0][0]['header']
                            st.markdown(f'#### {header}')
                            counter = 0
                            for subitem in sorted_df_dict[key]:
                                subitem_dict = subitem[0]
                                df_chart = subitem_dict['df']
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
                                    chart_html, bokeh_fig = bokeh_charts.overview_v1(
                                        df_chart,
                                        restart_headers,
                                        os_details,
                                        font_size=font_size,
                                        width=width,
                                        height=height,
                                        title=f"{header} {sub_title}" if sub_title else f"{header}",
                                    )
                                    st.components.v1.html(chart_html, height=height + 100, scrolling=True)
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
                                    # Optimize: only generate individual PDFs when not creating multi-PDF
                                    if create_multi_pdf:
                                        multi_pdf_chart_field.append(bokeh_fig)
                                        st.info("ℹ️ Chart will be included in the combined PDF at the bottom of the page.")
                                    else:
                                        pdf_name = f"{sar_file_name}_{helpers_pl.validate_convert_names(f'{title}_{sub_title}')}.pdf"
                                        lh.pdf_download_bokeh(bokeh_fig, pdf_name, key=pdf_name)
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
                        temp_pdf = mpdf.create_multi_pdf_from_bokeh_figures(multi_pdf_chart_field)
                        
                        # Read the PDF data and provide download button directly
                        with open(temp_pdf, 'rb') as f:
                            pdf_data = f.read()
                        
                        col1, _ = st.columns([0.2, 0.8])
                        col1.download_button(
                            label="Download Multi-PDF",
                            data=pdf_data,
                            file_name=download_name,
                            mime="application/pdf",
                            key="multi_pdf_download"
                        )
                        
                        # Clean up the temp file after reading
                        import os
                        if os.path.exists(temp_pdf):
                            os.remove(temp_pdf)
                        
                        # Clear chart objects from memory after PDF creation
                        multi_pdf_chart_field.clear()
                        del multi_pdf_chart_field
                        gc.collect()
                        
                    st.markdown("___")
                    # Back to top link using HTML anchor without page refresh
                    st.markdown(
                        """
                        <a href="#show-diagrams-section" 
                           style="display: inline-block; padding: 0.25rem 0.75rem; 
                                  text-decoration: none;">
                            ⬆️ Back to top
                        </a>
                        """,
                        unsafe_allow_html=True
                    )
                    
                    # Final cleanup: force garbage collection after all charts displayed
                    gc.collect()
