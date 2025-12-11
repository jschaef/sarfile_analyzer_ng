#!/usr/bin/python3
# handle_metrics compares different metrics
import streamlit as st
import alt
import polars as pl
import pl_helpers2 as pl_helpers
import helpers_pl as helpers
import metric_page_helpers_pl as mph
import layout_helper_pl as lh
from config import Config
from sqlite2_polars import get_sub_device_from_header


def do_metrics(
    config_dict: dict, username: str, sel_file: str, df: pl.DataFrame, os_details: str
) -> None:
    upload_dir = config_dict["upload_dir"]
    pdf_dir = f"{Config.upload_dir}/{username}/pdf"
    pdf_name = f"{pdf_dir}/{Config.pdf_name}"
    st.subheader("Compare different metrics")
    lh.make_vspace(5, st)
    sar_file = f"{upload_dir}/{sel_file}"
    df_complete = df
    os_field = []
    filename = sar_file.split("/")[-1]
    os_field.append({sar_file: os_details})
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
    cols = st.columns(4)
    collect_field, chart_field = mph.build_diff_metrics_menu(
        headers,
        sub_dev_headers_dict,
        df_complete,
        filename,
        os_details=os_details,
        reboot_headers=reboot_headers,
    )
    st.markdown("___")
    cols = st.columns(8)
    cols[7].write("\n")
    tab1, tab2, tab3 = st.tabs(["📈 Chart", "🗃 Data", " 📔 man page"])
    with tab1:
        chart_placeholder = st.empty()
        cols = st.columns(8)
        metrics_string = ""
        width, hight = helpers.diagram_expander(
            "Diagram Width", "Diagram Hight", cols[0]
        )
        font_size = helpers.font_expander(
            12, "Change Axis Font Size", "font size", cols[1]
        )
        chart = alt.overview_v4(chart_field, restart_headers, width, hight, font_size)
        with chart_placeholder:
            st.altair_chart(chart, theme=None)
        for field in collect_field:
            metric = field[2]
            if metrics_string:
                metrics_string = f"{metrics_string}-{metric}"
            else:
                metrics_string = f"{metric}"
        download_name = f"{filename}_{metrics_string}"
        download_name = f"{helpers.validate_convert_names(download_name)}.pdf"
        lh.pdf_download_direct(chart, download_name, key=f"pdf_{download_name}")
    with tab2:
        mph.display_stats_data(collect_field)
    with tab3:
        metrics = []
        for field in collect_field:
            metrics.append(field[2])
        cols = st.columns([0.6, 0.4])
        col1, _ = cols
        helpers.metric_popover(metrics, col=col1)
