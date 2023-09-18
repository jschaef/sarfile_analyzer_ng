#!/usr/bin/python3
import streamlit as st
import alt
import parse_into_polars as parse_polars
import pl_helpers2 as pl_helpers
import helpers_pl as helpers
import metric_page_helpers_pl as mph
import layout_helper_pl as lh
from config import Config
from sqlite2_polars import get_sub_device_from_header


def do_metrics(config_dict: dict, username: str) -> None:
    upload_dir = config_dict['upload_dir']
    pdf_dir = f'{Config.upload_dir}/{username}/pdf'
    pdf_name = f'{pdf_dir}/{Config.pdf_name}'
    _, _, col3, col4 = lh.create_columns(4,[1,1,0,1])
    sel_file = helpers.get_sar_files(username, col=col3)
    os_field = []

    col3, col4 = st.columns(2)

    radio_result = col4.radio('Choose, what to compare', ['Compare Different Metrics',
        'Compare same Metrics on Different Devices'], horizontal=True)
    if radio_result == 'Compare Different Metrics':
        col3.subheader('Compare Different Metrics')
        op_ph = col3.empty()
        op_ph1 = col3.empty()
    elif radio_result == 'Compare same Metrics on Different Devices':
        col3.subheader('Compare Same Metrics on Different Devices')
        op_ph = col3.empty()
        op_ph1 = col3.empty()
    st.markdown('___')

    sar_file = f'{upload_dir}/{sel_file}'
    filename = sar_file.split('/')[-1]
    df_complete = parse_polars.get_data_frame(sar_file, username)
    os_details = pl_helpers.get_os_details_from_df(df_complete)
    op_ph.write('Operating System Details:')
    op_ph1.write(os_details)
    os_field.append({sar_file: os_details})
    col3, col4 = st.columns(2)

    headers = pl_helpers.get_headers(df_complete)
    reboot_headers = helpers.extract_restart_header(headers)
    reboot_headers = pl_helpers.get_restart_headers(df_complete)

    restart_headers = [[reboot_headers]]
    restart_headers[0].append(os_details)
    sub_dev_headers = []
    headers_dict = []
    for header in headers:
        if get_sub_device_from_header(header):
            sub_dev_headers.append(header)
    sub_dev_headers.append("total/s dropd/s squeezd/s rx_rps/s flw_lim/s")
    sub_dev_headers.append("rcvin/s txmtin/s framerr/s prtyerr/s brk/s ovrun/s")
    for header in sub_dev_headers:
        headers_dict.append(helpers.translate_headers([header]))
    sub_dev_headers_dict = helpers.translate_headers(sub_dev_headers) 

    if radio_result == 'Compare same Metrics on Different Devices':
        # not_wanted = ['MHz']
        # for nw in not_wanted:
        #     if nw in sub_alias_headers:
        #         index = sub_alias_headers.index(nw)
        #         headers.pop(index)
        col3.write('Compare until 6 devices below')    
        cols = st.columns(4)

        chart_field, collect_field, prop = mph.create_metric_menu(cols, df_complete,  
            headers_dict, filename, os_details=os_details, reboot_headers=reboot_headers)
        title = f"{collect_field[0][3]} {collect_field[0][4]}"
        st.markdown('___')
        tab1, tab2, tab3 = st.tabs(["📈 Chart", "🗃 Data", " 📔 man page"])
        with tab1:
            cols = st.columns(8)
            width, hight = helpers.diagram_expander('Diagram Width',
              'Diagram Hight', cols[0])
            font_size = helpers.font_expander(12, "Change Axis Font Size", "font size", cols[1])
            chart= alt.overview_v5(chart_field, restart_headers, width, hight, 'device', font_size, title=title)
            st.markdown(f'###### {filename}')
            st.altair_chart(chart, theme=None)
            title = f"{filename}_{title}"
            download_name = f"{helpers.validate_convert_names(title)}.pdf"
            lh.pdf_download(pdf_name, chart, download_name=download_name)

        with tab2:
            mph.display_stats_data(collect_field)

        with tab3:
                helpers.metric_expander(prop, expand=False)

    elif radio_result == 'Compare Different Metrics':
        cols = st.columns(4)
        collect_field, chart_field = mph.build_diff_metrics_menu(headers, 
            sub_dev_headers_dict, df_complete, filename, os_details=os_details, 
            reboot_headers=reboot_headers)
        st.markdown('___')
        cols = st.columns(8)
        cols[7].write("\n")
        tab1, tab2, tab3 = st.tabs(["📈 Chart", "🗃 Data", " 📔 man page"])
        with tab1:
            cols = st.columns(8)
            metrics_string = ''
            width, hight = helpers.diagram_expander('Diagram Width',
                          'Diagram Hight', cols[0])
            font_size = helpers.font_expander(12, "Change Axis Font Size", "font size", cols[1])
            chart = alt.overview_v4(chart_field, restart_headers, width, hight, font_size )
            st.markdown(f'###### {filename}')
            st.altair_chart(chart, theme=None)
            for field in collect_field:
                metric = field[2]
                if metrics_string:
                    metrics_string = f"{metrics_string}-{metric}"
                else:
                    metrics_string = f"{metric}"
            download_name = f"{filename}_{metrics_string}"
            download_name = f"{helpers.validate_convert_names(download_name)}.pdf"
            lh.pdf_download(pdf_name, chart, download_name=download_name)
        with tab2:
            mph.display_stats_data(collect_field)
        with tab3:
            for field in collect_field:
                metric = field[2]
                helpers.metric_expander(metric, expand=False)