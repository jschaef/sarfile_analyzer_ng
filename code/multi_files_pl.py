#!/usr/bin/python3
# compare same metric on multiple sar files
import alt
import bokeh_charts
import streamlit as st
import helpers_pl as helpers
import pl_helpers2 as pl_helpers
import layout_helper_pl as lh
import parse_into_polars as parse_polars
import dia_compute_pl as dia_compute
import re
from os import path, listdir
from config import Config


def delete_session_state_df_obj(skey: str):
    keys_to_delete = []
    for key in st.session_state:
        if key.startswith(skey):
            keys_to_delete.append(key)
    helpers.clean_session_state(keys_to_delete)


def single_multi(config_dict: dict, username: str, ph_list: list):
    display_field = []
    upload_dir = config_dict["upload_dir"]
    pdf_dir = f"{Config.upload_dir}/{username}/pdf"
    pdf_name = f"{pdf_dir}/{Config.pdf_name}"
    cpu_aliases = re.compile(r"CPU|^soft.*", re.IGNORECASE)
    st.subheader("Compare same metric on multiple Sar Files")
    lh.make_vspace(3, st)
    sel_field = []
    for ph in ph_list:
        ph.empty()
    sar_files = [x for x in listdir(upload_dir) if path.isfile(f"{upload_dir}/{x}")]
    # exclude parquet files
    sar_files_pre = [x for x in sar_files if not x.endswith(".parquet")]
    sar_files = [x.replace(".parquet", "") for x in sar_files if x.endswith(".parquet")]
    sar_files.extend(sar_files_pre)

    sel_all = st.checkbox("***Select All***", key="select_all")
    st.write("\n")
    has_clicked = True if sel_all else False
    for file in sar_files:
        #key = f"sel_{sar_files.index(file)}_{file}"
        sel = st.checkbox(
            sar_files[sar_files.index(file)],
            #key=key,
            value=has_clicked,
            on_change=delete_session_state_df_obj,
            args=([file]),
        )
        if sel:
            sel_field.append(sar_files[sar_files.index(file)])

    col1, col2 = st.columns([0.3, 0.7])
    col1.markdown("___")

    col1, col2, col3, col4 = st.columns(4)
    col4.write("")
    ph_show = col1.empty()
    ph_choose = col3.empty()
    dia_type = ph_choose.toggle("Horizontal view for consecutive days",)
    if ph_show.checkbox("***show***", key="Show"):
        df_all = []
        all_headers = []
        os_field = []
        reboot_headers = []
        if sel_field:
            for file in sel_field:
                file = f"{upload_dir}/{file}"
                df_complete = parse_polars.get_data_frame(file, username)
                os_details = pl_helpers.get_os_details_from_df(df_complete)
                headers = pl_helpers.get_headers(df_complete)
                restart_headers = pl_helpers.get_restart_headers(df_complete)
                os_field.append(os_details)
                reboot_headers.append([restart_headers, os_details])
                all_headers.append(headers)
                df_all.append([df_complete, file])
            headers = helpers.merge_headers(all_headers)
            st.sidebar.markdown("---")
            selected, _ = helpers.get_selected_header("Sar Headings", headers)
            aitem = helpers.translate_headers([selected])
            main_title = aitem[selected]
            device_list = []
            df_list_header = []
            for sar_data in df_all:
                device_list_df = []
                df_file = sar_data[0]
                file = sar_data[1]
                df = pl_helpers.get_data_frames_from__headers(
                    [selected], df_file, "header"
                )[0]
                start = df["date"].min()
                end = df["date"].max()
                if not cpu_aliases.search(aitem[selected]):
                    df_list = dia_compute.prepare_df_for_pandas(df, start, end)
                    for index in df_list:
                        if index["sub_title"] not in device_list_df:
                            device_list_df.append(index["sub_title"])
                    df_list_header.append([df_list, file])
                    device_list.append(device_list_df)
                else:
                    tmp_device_list = dia_compute.get_device_list(df)
                    for device in tmp_device_list:
                        if device not in device_list_df:
                            device_list_df.append(device)
                    device_list.append(device_list_df)
                    df_list_header.append([df, file])
            if device_list:
                sub_items = helpers.merge_headers(device_list)
            if len(sub_items) >= 1 and sub_items[0].strip():
                sub_item = st.sidebar.selectbox(
                    "Choose devices", [key for key in sub_items], key="sub"
                )
                header_add = sub_item
            else:
                sub_item = None
                header_add = ""
            # choose the first df for getting the metrics
            if not cpu_aliases.search(aitem[selected]):
                for index in range(len(df_list_header)):
                    file_name = path.basename(df_list_header[index][1])
                    delete_session_state_df_obj(file_name)

                arbitrary_df = df_list_header[0][0][0]["df"]
            else:
                for index in range(len(df_list_header)):
                    # start_time = helpers.measure_time()
                    index_df = df_list_header[index][0]
                    file_name = path.basename(df_list_header[index][1])
                    df_list_header[index][
                        0
                    ] = dia_compute.prepare_single_device_for_pandas(
                        index_df, start, end, sub_item, file_name
                    )
                    # helpers.measure_time(prop='end',start_time=start_time)
                arbitrary_df = df_list_header[0][0][0]["df"]
            prop_box = st.sidebar.empty()
            prop = prop_box.selectbox(
                "metric", [col for col in arbitrary_df], key="prop"
            )
            title = f"{main_title} {sub_item}" if sub_item else main_title

            if df_list_header:
                chart_field = []
                pd_or_dia = col1.selectbox(
                    "dia", ["Diagram", "Summary"], index=0, label_visibility="hidden"
                )
                collect_field = []
                dia_collect_field = []
                sum_field = []

                for sub_list1 in df_list_header:
                    df_list = sub_list1[0]
                    file = sub_list1[1]
                    file = file.split("/")[-1]
                    if len(df_list) > 1:
                        for device in df_list:
                            if device["sub_title"] == sub_item:
                                df = device["df"]
                                break
                    else:
                        df = df_list[0]["df"]

                    df1 = df.copy(deep=True)
                    df_part = df[[prop]].copy()
                    df_part["file"] = file
                    df_part["date"] = df_part.index
                    chart_field.append([df_part, prop])
                    sum_field.append({file: [df1]})
                    dia_collect_field.append([file, df1])
                    df1 = df1.reset_index().melt(
                        "date", var_name="metrics", value_name="y"
                    )
                    collect_field.append({file: [df1]})

            if pd_or_dia == "Diagram":
                if chart_field:
                    start_list = [
                        chart_field[x][0].sort_index().index[0]
                        for x in range(len(chart_field))
                    ]
                    end_list = [
                        chart_field[x][0].sort_index().index[-1]
                        for x in range(len(chart_field))
                    ]
                    start = helpers.get_start_end_date(start_list, "start")
                    end = helpers.get_start_end_date(end_list, "end")
                    col1, col2, col3, col4, *_ = st.columns(8)
                    if not dia_type:
                        start, end = helpers.create_start_end_time_list(
                            start, end, col1, col2
                        )
                        for item in range(len(chart_field)):
                            df_date = helpers.get_df_from_start_end(
                                chart_field[item][0], start, end
                            )
                            chart_field[item][0] = df_date.sort_index()
                    col1, col2, col3, col4 = st.columns(4)
                    col3.write(""), col4.write()
                    if not dia_type:
                        tab1, tab2, tab3, tab4 = st.tabs( ["📈 Chart", "🗃 Data", "🧮 Statistics", " 📔 man page"])
                    else:
                        tab1, tab2, = st.tabs( ["📈 Chart",  " 📔 man page"])
                    with tab1:
                        cols = st.columns(8)
                        font_size = helpers.font_expander(
                            12, "Change Axis Font Size", "font size", cols[1]
                        )
                        width, hight = helpers.diagram_expander(
                            "Diagram Width", "Diagram Hight", col=cols[0]
                        )
                        chart_lib = cols[2].radio("Chart Library", ["Bokeh", "Altair"], index=0, key="multi_compare_lib", horizontal=True)
                        
                        chart_placeholder = st.empty()
                        
                        if chart_lib == "Bokeh":
                            if dia_type:
                                chart_html, bokeh_fig = bokeh_charts.overview_v3(
                                    chart_field,
                                    reboot_headers,
                                    width,
                                    hight,
                                    "file",
                                    font_size,
                                    title=title,
                                )
                            else:
                                chart_html, bokeh_fig = bokeh_charts.overview_v6(
                                    chart_field,
                                    reboot_headers,
                                    width,
                                    hight,
                                    font_size,
                                    title=title,
                                )
                            with chart_placeholder:
                                st.components.v1.html(chart_html, height=hight+100, scrolling=True)
                        else:
                            if dia_type:
                                img = alt.overview_v3(
                                    chart_field,
                                    reboot_headers,
                                    width,
                                    hight,
                                    "file",
                                    font_size,
                                    title=title,
                                )
                            else:
                                img = alt.overview_v6(
                                    chart_field,
                                    reboot_headers,
                                    width,
                                    hight,
                                    font_size,
                                    title=title,
                                )
                            img = img.configure_axisY(labelLimit=400)
                            with chart_placeholder:
                                st.altair_chart(img, theme=None)
                        
                        if not dia_type:
                            metric = chart_field[0][1]
                            title = f"{title}_{metric}"
                            download_name = f"{helpers.validate_convert_names(title)}.pdf"
                            download_name = f"multi_files_{download_name}"
                            
                            if chart_lib == "Bokeh":
                                lh.pdf_download_bokeh(bokeh_fig, download_name, key=download_name)
                            else:
                                lh.pdf_download_direct(img, download_name, key=download_name)
                    if not dia_type:
                        with tab2:
                            object_field = []
                            if chart_field:
                                prop = chart_field[0][1]
                                for index in dia_collect_field:
                                    restart_headers = []
                                    os_details = ""
                                    filename = index[0]
                                    df_stat = index[1]
                                    df_new = df_stat[[prop]].copy()
                                    df_time = helpers.get_df_from_start_end(
                                        df_new.copy(), start, end
                                    )
                                    df_time = df_time.loc[~df_time.index.duplicated(), :]
                                    index[1][prop] = df_time
                                    for event in reboot_headers:
                                        hostname = event[1].split()[2].strip("()")
                                        date = event[1].split()[3]
                                        if hostname in filename:
                                            if date in filename:
                                                restart_headers = event[0]
                                                os_details = event[1]
                                                break
                                    stats = df_time.describe()
                                    table = helpers.restart_headers(
                                        df_time,
                                        os_details,
                                        restart_headers=restart_headers,
                                        display=False,
                                    )
                                    header = filename
                                    object_field.append([table, stats, header])
                            lh.arrange_grid_entries(object_field, 4)
                    else:
                        with tab2:
                            col1, col2 = st.columns([0.6, 0.4])
                            lh.show_metrics([prop], checkbox="off", col=col1)
                    if not dia_type:
                        with tab3:
                            prop = chart_field[0][1]
                            lh.display_averages(
                                dia_collect_field, prop, main_title, sub_item
                            )
                        with tab4:
                            col1, col2 = st.columns([0.6, 0.4])
                            lh.show_metrics([prop], checkbox="off", col=col1)
            elif pd_or_dia == "Summary":
                ph_choose.empty()
                prop_box.empty()
                for data in sum_field:
                    for key in data:
                        st.text("")
                        filename = f'{key.split("/")[-1]}'
                        for header in reboot_headers:
                            hostname = header[1].split()[2].strip("()")
                            if hostname in filename:
                                os_details = header[1]
                        df = data[key][0]
                        ds = df.describe()
                        df_display = df.copy()
                        display_field.append(
                            [key, df_display, ds, aitem, selected, header_add]
                        )

                for data in collect_field:
                    for key in data:
                        st.text("")
                        st.markdown(f"##### {key}")
                        restart_headers = []
                        for event in reboot_headers:
                            hostname = event[1].split()[2].strip("()")
                            date = event[1].split()[3]
                            if hostname in key and date in key:
                                restart_headers = event[0]
                                os_details = event[1]
                                break
                        df = data[key][0]

                        tab1, tab2, tab3 = st.tabs(["📈 Chart", "🗃 Data", " 📔 man page"])
                        with tab1:
                            chart_placeholder = st.empty()
                            cols = st.columns(8)
                            width, height = helpers.diagram_expander(
                                "Diagram Width", "Diagram Hight", col=cols[0], key=key
                            )
                            font_size = helpers.font_expander(
                                12,
                                "Change Axis Font Size",
                                "font size",
                                cols[1],
                                key=f"slider_{key}",
                            )
                            chart_lib = cols[2].radio("Chart Library", ["Bokeh", "Altair"], index=0, key=f"multi_overview_{key}", horizontal=True)
                            
                            if chart_lib == "Bokeh":
                                chart_html, bokeh_fig = bokeh_charts.overview_v1(
                                    df,
                                    restart_headers,
                                    os_details,
                                    font_size,
                                    width=width,
                                    height=height,
                                    title=title,
                                )
                                with chart_placeholder:
                                    st.components.v1.html(chart_html, height=height+100, scrolling=True)
                                dia_key = f"dia_{collect_field.index(data)}"
                                download_name = (
                                    f"{key}_{helpers.validate_convert_names(title)}.pdf"
                                )
                                lh.pdf_download_bokeh(bokeh_fig, download_name, key=dia_key)
                            else:
                                chart = alt.overview_v1(
                                    df,
                                    restart_headers,
                                    os_details,
                                    font_size,
                                    width=width,
                                    height=height,
                                    title=title,
                                )
                                with chart_placeholder:
                                    st.altair_chart(chart, theme=None)
                                dia_key = f"dia_{collect_field.index(data)}"
                                download_name = (
                                    f"{key}_{helpers.validate_convert_names(title)}.pdf"
                                )
                                lh.pdf_download_direct(chart, download_name, key=dia_key)
                            st.markdown("#####")
                        with tab2:
                            for entry in display_field:
                                if entry[0] == key:
                                    cols = st.columns(2)
                                    col1, _ = cols
                                    col1.markdown("#####")
                                    df_display = entry[1]
                                    ds = entry[2]
                                    aitem = entry[3]
                                    selected = entry[4]
                                    header_add = entry[5]
                                    col1.markdown(
                                        f"###### Data for {aitem[selected]} {header_add}"
                                    )
                                    helpers.restart_headers(
                                        df_display,
                                        os_details,
                                        restart_headers=restart_headers, col=col1
                                    )
                                    col1.markdown(
                                        f"###### Statistics for {aitem[selected]} {header_add}"
                                    )
                                    col1.write(ds)
                                    st.markdown("#####")
                        with tab3:
                            for entry in display_field:
                                if entry[0] == key:
                                    df_display = entry[1]
                                    cols = st.columns([0.6, 0.4])
                                    col1, _ = cols
                                    metrics = df_display.columns.to_list()
                                    helpers.metric_popover(metrics, col=col1)
    else:
        keys_to_delete = []
        for key in st.session_state:
            if key.endswith("_end") or key.endswith("_start") or key.endswith("_obj"):
                keys_to_delete.append(key)
        helpers.clean_session_state("multi_start", "multi_end")
        helpers.clean_session_state(keys_to_delete)
