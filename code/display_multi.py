#!/usr/bin/python3
import streamlit as st
import polars as pl
import helpers_pl
import alt
import bokeh_charts
import pl_helpers2 as pl_h2
import sqlite2_polars as s2p
import layout_helper_pl as lh
import sqlite2_polars
from config import Config


file_chosen = ""


def show_multi(config_obj, username, selection, df, os_details):
    global file_chosen, df_complete
    pdf_dir = f"{Config.upload_dir}/{username}/pdf"
    upload_dir = config_obj["upload_dir"]
    pdf_name = f"{pdf_dir}/{Config.pdf_name}"
    cache_obj = ""
    description = """This page is for finding metrics which have been measured\
    on multiple devices. E.g. showing all CPU's where iowait is above 15.5 and\
    below 50.0. at a certain  time frame"""
    col1, col2 = st.columns([0.7, 0.3])
    col1.subheader(description)
    lh.make_vspace(1, col1)
    col1, col2, col3, _ = st.columns([1, 1, 1, 1])
    col2.write("")
    st.sidebar.markdown("---")
    # parse data from file
    sar_file = f"{upload_dir}/{selection}"
    if sar_file != file_chosen:
        lh.delete_large_obj()
        file_chosen = sar_file
    df_complete = df
    headers = pl_h2.get_headers(df_complete)
    restart_headers = pl_h2.get_restart_headers(df_complete)
    alias_dict = helpers_pl.translate_headers(headers)
    wanted_headers = {}
    for key, value in alias_dict.items():
        if s2p.get_sub_device_from_header(key):
            wanted_headers[key] = value
    rev_wanted_headers = {v: k for k, v in wanted_headers.items()}
    selected = st.sidebar.selectbox("Sar Headings", sorted(list(wanted_headers.values())))
    headerline = rev_wanted_headers[selected]
    header = selected
    if "SOFT" in header:
        header = "SOFT"
    cache_obj = f"{sar_file.split('/')[-1]}_{header}_obj"
    df_state = st.session_state.get(cache_obj, [])
    if df_state:
        if not df_state[1] == sar_file:
            selected_df = pl_h2.get_data_frames_from__headers(
                [headerline], df_complete, "header"
            )[0]
            helpers_pl.set_state_key(cache_obj, value=selected_df, change_key=sar_file)
        else:
            selected_df = st.session_state[cache_obj][0]
    else:
        selected_df = pl_h2.get_data_frames_from__headers(
            [headerline], df_complete, "header"
        )[0]
        helpers_pl.set_state_key(cache_obj, value=selected_df, change_key=sar_file)
    df = selected_df
    device_list = []
    device_list_name = f"device_list_{header}_obj"
    device_list_state = st.session_state.get(device_list_name, [])
    header = selected
    file_name = sar_file.split("/")[-1]
    if "SOFT" in header:
        header = "SOFT"
    large_df_key = f"large_df_{file_name}_{header}_obj"
    if device_list_state:
        if not device_list_state[1] == sar_file:
            large_df = pl_h2.get_metrics_from_df(df, headerline, selected)
            device_list = pl_h2.get_sub_devices_from_df(large_df, "sub_device")
            device_list.sort()
            if "all" in device_list:
                device_list.remove("all")
            helpers_pl.set_state_key(
                device_list_name, value=device_list, change_key=sar_file
            )
            helpers_pl.set_state_key(large_df_key, value=large_df, change_key=sar_file)
        else:
            device_list = st.session_state.get(device_list_name)[0]
            if "all" in device_list:
                device_list.remove("all")
            if st.session_state.get(large_df_key, []):
                large_df = st.session_state.get(large_df_key)[0]
            else:
                large_df = pl_h2.get_metrics_from_df(df, headerline, selected)
                helpers_pl.set_state_key(
                    large_df_key, value=large_df, change_key=sar_file
                )
    else:
        large_df = pl_h2.get_metrics_from_df(df, headerline, selected)
        device_list = pl_h2.get_sub_devices_from_df(large_df, "sub_device")
        device_list.sort()
        if "all" in device_list:
            device_list.remove("all")
        helpers_pl.set_state_key(
            device_list_name, value=device_list, change_key=sar_file
        )
        helpers_pl.set_state_key(large_df_key, value=large_df, change_key=sar_file)
    if isinstance(device_list[1], int):
        device_list = [int(x) for x in device_list]
        device_list.insert(0, "all")
    device_list.sort()
    metric = st.sidebar.selectbox("metric", headerline.split())
    metric_df = pl_h2.create_metric_df(large_df, headerline, metric)
    slider_max = round(metric_df[metric].max(), 2)
    slider_min = round(metric_df[metric].min(), 2)
    step = round(slider_max / 20, 2)
    options = []
    start = 0
    while start < slider_max:
        options.append(round(start, 2))
        start += step
    options.append(slider_max)
    col1, col2 = st.columns([1, 1])
    if slider_min != slider_max:
        metric_index = headerline.split().index(metric)
        help = f"""select a min, max range for {metric} which will be 
        displayed in the table below"""
        min, max = col1.select_slider(
            "Select a threshold range",
            options,
            value=(options[0], options[10]),
            help=help,
        )
        filtered_df = large_df.filter(pl.col(headerline).list.get(metric_index) >= min)
        filtered_df = filtered_df.filter(
            pl.col(headerline).list.get(metric_index) <= max
        )
        lh.make_vspace(1, col1)
        present_df = pl_h2.create_metric_df2(filtered_df, headerline, metric)
        start = present_df["date"].min()
        end = present_df["date"].max()
        col1, col2, col3, _ = st.columns([0.25, 0.25, 0.05, 0.4])
        start_df, end_df = helpers_pl.create_start_end_time_list(start, end, col1, col2)
        lh.make_vspace(1, col3)
        if start_df and end_df:
            present_df = pl_h2.filter_df_by_range(present_df, "date", start_df, "gt")
            present_df = pl_h2.filter_df_by_range(present_df, "date", end_df, "lt")
            lh.make_vspace(2, col1)
            lh.make_vspace(2, col2)
            col1 = st.columns(2)[0]
            col1.caption(
                """If you want to see a graphical presentation 
                of some of these subdevices click on the select box beneath 
                the device name or select all to see all devices""",
            )
            col1, col2, col3, _ = st.columns([0.25, 0.25, 0.05, 0.4])
            col1.dataframe(present_df)
            sub_devs_df = present_df.drop(["date", metric])
            ph_col2 = col2.empty()
            res_devlist = pl_h2.dataframe_editor(
                sub_devs_df, ph_col2, 1, "Select for diagram"
            )
            if col3.checkbox("select all"):
                res_devlist = pl_h2.dataframe_editor(
                    sub_devs_df, ph_col2, 1, "Select for diagram", True
                )
            dev_list = res_devlist[0]["sub_device"].to_list()
            if dev_list:
                if col1.checkbox("Show diagrams") and dev_list:
                    filtered_df = large_df.filter(pl.col("sub_device").is_in(dev_list))
                    filtered_df = pl_h2.create_metric_df2(filtered_df, headerline, metric)

                    tab1, tab2 = st.tabs(["📈 Chart", " 📔 man page"])
                    with tab1:
                        chart_placeholder = st.empty()
                        cols = st.columns(8)
                        width, hight = helpers_pl.diagram_expander(
                            "Diagram Width", "Diagram Hight", cols[0]
                        )
                        font_size = helpers_pl.font_expander(
                            12, "Change Axis Font Size", "font size", cols[1]
                        )
                        chart_lib = cols[2].radio(
                            "Chart Library",
                            ["Bokeh", "Altair"],
                            index=0,
                            key="multi_device_chart_lib",
                            horizontal=True,
                        )

                        if chart_lib == "Bokeh":
                            # Bokeh expects pandas for dt access + ColumnDataSource
                            b_df = filtered_df.to_pandas()
                            chart_html, bokeh_fig = bokeh_charts.overview_v5(
                                b_df,
                                metric,
                                file_name,
                                restart_headers,
                                width,
                                hight,
                                "sub_device",
                                font_size,
                                os_details,
                                title=f"{selected} {metric}",
                            )
                            with chart_placeholder:
                                st.components.v1.html(chart_html, height=hight + 100, scrolling=True)
                            download_name = f"{helpers_pl.validate_convert_names(f'{file_name}_{selected}_{metric}')}.pdf"
                            lh.pdf_download_bokeh_direct(
                                bokeh_fig,
                                download_name,
                                key=f"pdf_{file_name}_{selected}_{metric}"
                            )
                        else:
                            chart = alt.overview_v5(
                                filtered_df,
                                metric,
                                file_name,
                                [restart_headers],
                                width,
                                hight,
                                "sub_device",
                                font_size,
                                os_details,
                                title=f"{selected} {metric}",
                            )
                            with chart_placeholder:
                                st.altair_chart(chart, width='stretch', theme=None)
                            lh.pdf_download_direct(
                                chart,
                                f"{helpers_pl.validate_convert_names(f'{file_name}_{selected}_{metric}')}.pdf",
                                key=f"pdf_{file_name}_{selected}_{metric}",
                            )
                    with tab2:
                        cols = st.columns([0.55, 0.45])
                        col1, _ = cols
                        description = sqlite2_polars.ret_metric_description(metric)
                        col1.markdown(description)
        else:
            col1.info("No data available for selected time frame")


    else:
        col1.write(f"No threshold available. Metric is constant at {slider_min}")
