import streamlit as st
import polars as pl
import layout_helper_pl as lh
import helpers_pl
import alt
import re
import pl_helpers2 as pl_h2
import dia_compute_pl as dia_compute
from config import Config

file_chosen = ""
df_complete = None
def single_f(config_obj, username, selection, df, os_details):
    perf_intensive_metrics = re.compile(r'^CPU|SOfT.*', re.IGNORECASE)
    global file_chosen, df_complete
    pdf_dir = f'{Config.upload_dir}/{username}/pdf'
    pdf_name = f'{pdf_dir}/{Config.pdf_name}'
    st.subheader("Show metrics for a single sar file")
    col1, col2, col3, _ = st.columns([1,1,1, 1])
    lh.make_vspace(1, col1)
    des_text = 'Show a Summary of the chosen header or Details of the chosen metric in the left frame'
    selected_content = col1.selectbox(
            des_text, ['Details','Summary'], key='diagr')
    col2.write('')
    st.sidebar.markdown('---')
    sar_file = selection
    if sar_file != file_chosen:
        lh.delete_large_obj()
        file_chosen = sar_file
    df_complete = df
    headers = pl_h2.get_headers(df_complete)
    restart_headers = pl_h2.get_restart_headers(df_complete)
    selected, _ = helpers_pl.get_selected_header('Sar Headings', headers)
    aitem = helpers_pl.translate_headers([selected])
    # get dataframe for selected header, time consuming on big files
    if not perf_intensive_metrics.search(aitem[selected]):
        df = pl_h2.get_data_frames_from__headers([selected], df_complete, "header")[0]
    else:
        header = aitem[selected]
        if "SOFT" in header:
            header = "SOFT"
        cache_obj = f"{sar_file.split('/')[-1]}_{header}_obj"
        df_state = st.session_state.get(cache_obj, [])
        if df_state:
            if not df_state[1] == sar_file:
                selected_df = pl_h2.get_data_frames_from__headers([selected],
                    df_complete, "header")[0]
                helpers_pl.set_state_key(cache_obj, value=selected_df, 
                    change_key=sar_file)
            else:
                selected_df = st.session_state[cache_obj][0]
        else:
            selected_df = pl_h2.get_data_frames_from__headers([selected],
                df_complete, "header")[0]
            helpers_pl.set_state_key(cache_obj, value=selected_df, change_key=sar_file)
        df = selected_df
    start = df['date'].min()
    end = df['date'].max()

    device_list = []
    # time consuming on big files
    if not perf_intensive_metrics.search(aitem[selected]):
        df_list = dia_compute.prepare_df_for_pandas(df, start, end)
    else:
        device_list_state = st.session_state.get('device_list', [])
        header = aitem[selected]
        file_name = sar_file.split('/')[-1]
        if "SOFT" in header:
            header = "SOFT"
        large_df_key = f"large_df_{file_name}_{header}_obj"
        if device_list_state:
            if not device_list_state[1] == sar_file:
                large_df = pl_h2.get_metrics_from_df(df, selected, aitem[selected])
                device_list = pl_h2.get_sub_devices_from_df(large_df, 'sub_device')
                device_list.sort()
                if 'all' in device_list:
                    device_list.remove('all')
                helpers_pl.set_state_key('device_list', value=device_list, change_key=sar_file)
                helpers_pl.set_state_key(large_df_key, value=large_df, change_key=sar_file)
            else:
                device_list = st.session_state.device_list[0]
                if 'all' in device_list:
                    device_list.remove('all')
                if st.session_state.get(large_df_key, []):
                    large_df = st.session_state.get(large_df_key)[0]
                else:
                    large_df = pl_h2.get_metrics_from_df(df, selected, aitem[selected])
                    helpers_pl.set_state_key(large_df_key, value=large_df, change_key=sar_file)
        else:
            large_df = pl_h2.get_metrics_from_df(df, selected, aitem[selected])
            device_list = pl_h2.get_sub_devices_from_df(large_df, 'sub_device')
            device_list.sort()
            if 'all' in device_list:
                device_list.remove('all')
            helpers_pl.set_state_key('device_list', value=device_list, change_key=sar_file)
            helpers_pl.set_state_key(large_df_key, value=large_df, change_key=sar_file)
        device_list = [int(x) for x in device_list]
        device_list.sort()
        device_list.insert(0, 'all')

    sub_item = ''
    if not perf_intensive_metrics.search(aitem[selected]):
        for index in df_list:
            df = index['df']
            device_list.append(index['sub_title'])

    if selected_content == 'Details':
        if len(device_list) > 1:
            sub_item = st.sidebar.selectbox('Choose Devices', device_list)
            if perf_intensive_metrics.search(aitem[selected]):
                df = pl_h2.get_df_from_sub_device(large_df, 'sub_device', str(sub_item))
                df = pl_h2.create_metrics_df(df, selected)
                df = df.select(pl.all().shrink_dtype()).to_pandas().set_index('date')

            else:
                for index in df_list:
                    if index['sub_title'] == sub_item:
                        df = index['df']
                        break
        else: 
            df = df_list[0]['df']

        if sub_item or sub_item == 0:
            header_add = sub_item
            title = f"{aitem[selected]} {sub_item}"
        else:
            header_add =''
            title = aitem[selected]

        prop = st.sidebar.selectbox('metrics', [
            metric for metric in df.columns])

        df_part = df[prop].copy().to_frame()
        df_displ = df_part.copy()
        helpers_pl.restart_headers(
            df_part, os_details, restart_headers=restart_headers, display=None)
        df_part['file'] = os_details.split()[2].strip('()')
        df_part['date'] = df_part.index
        df_part['metric'] = prop

        tab1, tab2, tab3 = st.tabs(["📈 Chart", "🗃 Data", " 📔 man page"])
        with tab1:
            chart_placeholder = st.empty()
            cols = st.columns(8)
            width, hight = helpers_pl.diagram_expander('Diagram Width', 'Diagram Hight', cols[0])
            font_size = helpers_pl.font_expander(12, "Change Axis Font Size", "font size", cols[1])
            chart = alt.draw_single_chart_v1(
                df_part, prop, restart_headers, os_details, width, hight, font_size=font_size, title=title)
            with chart_placeholder.container():
                st.altair_chart(chart, theme=None)
            title = f"{title}_{prop}"
            download_name = f"{selection}_{helpers_pl.validate_convert_names(title)}.pdf"
            lh.pdf_download(pdf_name, chart, download_name=download_name)
        with tab2:
            cols = st.columns(2)
            col1, _ = cols
            col1.markdown("#####")
            col1.markdown(f'###### Dataset for {aitem[selected]} {header_add} {prop}')
            helpers_pl.restart_headers(df_displ, os_details, restart_headers=restart_headers, col=col1)
            col1.markdown(f'###### Statistics for {aitem[selected]} {header_add} {prop}')
            col1.dataframe(df_displ.describe())
        with tab3:
            col1, col2 = st.columns(2)
            lh.show_metrics([prop], checkbox="off", col=col1)
    if selected_content == 'Summary':
        col1, col2, col3, _ = st.columns(4)
        if len(device_list) > 1:
            sub_item = st.sidebar.selectbox('Choose Devices', device_list)
            if perf_intensive_metrics.search(aitem[selected]):
                df = pl_h2.get_df_from_sub_device(large_df, 'sub_device', str(sub_item))
                df = pl_h2.create_metrics_df(df, selected)
                df = df.select(pl.all().shrink_dtype()).to_pandas().set_index('date')

            else:
                for index in df_list:
                    if index['sub_title'] == sub_item:
                        df = index['df']
                        break
        else:
            df = df_list[0]['df']

        if sub_item or sub_item == 0:
            header_add = sub_item
            title = f"{aitem[selected]} {sub_item}"
        else:
            header_add =''
            title = aitem[selected]

        x_list = []
        y_list = []
        for metric in df.columns.to_list():
            x_list.append(df[metric].idxmin())
            y_list.append(df[metric].idxmax())

        df_displ = df.copy()

        helpers_pl.restart_headers(df, os_details, restart_headers=restart_headers, display=False)
        df = df.reset_index().melt('date', var_name='metrics', value_name='y')
        tab1, tab2, tab3 = st.tabs(["📈 Chart", "🗃 Data", " 📔 man page"])
        with tab1:
            chart_placeholder = st.empty()
            cols = st.columns(8)
            width, height = helpers_pl.diagram_expander('Diagram Width', 'Diagram Hight', cols[0])
            font_size = helpers_pl.font_expander(12, "Change Axis Font Size", "font size", cols[1])
            chart = alt.overview_v1(df, restart_headers, os_details, font_size=font_size, width=width, 
                height=height, title=title)
            with chart_placeholder.container():
                st.altair_chart(chart, theme=None)
            download_name = f"{selection}_{helpers_pl.validate_convert_names(title)}.pdf"
            lh.pdf_download(pdf_name, chart, download_name=download_name)
        with tab2:
            cols = st.columns(2)
            col1, _ = cols
            col1.markdown("#####")
            col1.markdown(f'###### Dataset for {aitem[selected]} {header_add}')
            helpers_pl.restart_headers(df_displ, os_details, restart_headers=restart_headers, col=col1)
            col1.markdown(f'###### Statistics for {aitem[selected]} {header_add}')
            col1.text('')
            col1.write(df_displ.describe())
        with tab3:
            cols = st.columns([0.6, 0.4])
            col1, _ = cols
            metrics = df['metrics'].drop_duplicates().tolist()
            helpers_pl.metric_popover(metrics, col=col1)
