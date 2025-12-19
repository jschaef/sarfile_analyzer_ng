#!/usr/bin/python3
"""
Bokeh Demo Page - Performance comparison with Altair
Demonstrates fast rendering and efficient handling of large datasets with Bokeh
"""
import streamlit as st
import streamlit.components.v1 as components
import layout_helper_pl as lh
import helpers_pl
import pl_helpers2 as pl_h2
import dia_compute_pl as dia_compute
from bokeh.plotting import figure
from bokeh.models import HoverTool, CrosshairTool, ResetTool, PanTool, WheelZoomTool
from bokeh.models import DatetimeTickFormatter, Span
from bokeh.embed import file_html
from bokeh.resources import CDN
import re
import time

file_chosen = ""
df_complete = None

def bokeh_demo(config_obj, username, selection, df, os_details):
    """
    Bokeh demonstration page showing improved performance over Altair.
    Uses the same data flow but renders with Bokeh for comparison.
    """
    perf_intensive_metrics = re.compile(r'^CPU|SOfT.*', re.IGNORECASE)
    global file_chosen, df_complete
    
    st.subheader("⚡ Bokeh Performance Demo")
    st.info("""
    **Why Bokeh?** This page demonstrates Bokeh as a high-performance alternative to Altair:
    - 🚀 **Excellent for large datasets** (handles 100k+ points smoothly)
    - 💾 **Efficient server-side rendering** reduces browser load
    - 🎯 **Built-in tools** for pan, zoom, hover, and more
    - 📊 Same data, different visualization engine
    """)
    
    col1, col2, col3, _ = st.columns([1, 1, 1, 1])
    lh.make_vspace(1, col1)
    
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
    
    # Get dataframe for selected header
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
                helpers_pl.set_state_key(cache_obj, value=selected_df, change_key=sar_file)
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
    # Time consuming on big files
    if not perf_intensive_metrics.search(aitem[selected]):
        df_list = dia_compute.prepare_df_for_pandas(df, start, end)
    else:
        device_list_state = st.session_state.get('device_list', [])
        header = aitem[selected]
        file_name = sar_file.split('/')[-1]
        if "SOFT" in header:
            header = "SOFT"
        large_df_key = f"large_df_{file_name}_{header}_obj"
        # Store the original unprocessed df for later use
        original_df_key = f"original_df_{file_name}_{header}_obj"
        if device_list_state:
            if not device_list_state[1] == sar_file:
                large_df = pl_h2.get_metrics_from_df(df, selected, aitem[selected])
                device_list = pl_h2.get_sub_devices_from_df(large_df, 'sub_device')
                device_list.sort()
                if 'all' in device_list:
                    device_list.remove('all')
                helpers_pl.set_state_key('device_list', value=device_list, change_key=sar_file)
                helpers_pl.set_state_key(large_df_key, value=large_df, change_key=sar_file)
                helpers_pl.set_state_key(original_df_key, value=df, change_key=sar_file)
            else:
                device_list = st.session_state.device_list[0]
                if 'all' in device_list:
                    device_list.remove('all')
                if st.session_state.get(large_df_key, []):
                    large_df = st.session_state.get(large_df_key)[0]
                else:
                    large_df = pl_h2.get_metrics_from_df(df, selected, aitem[selected])
                    helpers_pl.set_state_key(large_df_key, value=large_df, change_key=sar_file)
                    helpers_pl.set_state_key(original_df_key, value=df, change_key=sar_file)
        else:
            large_df = pl_h2.get_metrics_from_df(df, selected, aitem[selected])
            device_list = pl_h2.get_sub_devices_from_df(large_df, 'sub_device')
            device_list.sort()
            if 'all' in device_list:
                device_list.remove('all')
            helpers_pl.set_state_key('device_list', value=device_list, change_key=sar_file)
            helpers_pl.set_state_key(large_df_key, value=large_df, change_key=sar_file)
            helpers_pl.set_state_key(original_df_key, value=df, change_key=sar_file)
        device_list = [int(x) for x in device_list]
        device_list.sort()
        device_list.insert(0, 'all')
    
    sub_item = ''
    if not perf_intensive_metrics.search(aitem[selected]):
        for index in df_list:
            df_pandas = index['df']
            device_list.append(index['sub_title'])
    
    if len(device_list) > 1:
        sub_item = st.sidebar.selectbox('Choose Devices', device_list)
        if perf_intensive_metrics.search(aitem[selected]):
            # Get the original unprocessed df for prepare_single_device_for_pandas
            original_df_key = f"original_df_{file_name}_{header}_obj"
            original_df = st.session_state.get(original_df_key, [df])[0]
            df_pandas = dia_compute.prepare_single_device_for_pandas(
                original_df, start, end, sub_item, file_name
            )[0]['df']
        else:
            for entry in df_list:
                if entry['sub_title'] == sub_item:
                    df_pandas = entry['df']
                    break
    else:
        df_pandas = df_list[0]['df']
    
    if sub_item or sub_item == 0:
        header_add = sub_item
        title = f"{aitem[selected]} {sub_item}"
    else:
        header_add = ''
        title = aitem[selected]
    
    prop = st.sidebar.selectbox('metrics', [metric for metric in df_pandas.columns])
    
    # Prepare data
    df_chart = df_pandas[[prop]].copy()
    df_chart['date'] = df_pandas.index
    
    # Convert to Python datetime for Bokeh
    df_chart = df_chart.reset_index(drop=True)
    
    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["📈 Bokeh Chart", "⚡ Performance Info", "🗃 Data"])
    
    with tab1:
        st.markdown(f"### {title} - {prop}")
        
        # Measure rendering time
        render_start = time.perf_counter()
        
        # Create Bokeh figure
        p = figure(
            title=f"{title} - {prop}",
            x_axis_label='Time',
            y_axis_label=prop,
            x_axis_type='datetime',
            width=900,
            height=500,
            toolbar_location="above",
        )
        
        # Add line
        line = p.line(
            x='date',
            y=prop,
            source=df_chart,
            line_width=2,
            color='#1f77b4',
            alpha=0.8
        )
        
        # Add hover tool
        hover = HoverTool(
            tooltips=[
                ('Time', '@date{%F %T}'),
                (prop, f'@{prop}{{0.00}}'),
            ],
            formatters={'@date': 'datetime'},
            mode='vline'
        )
        p.add_tools(hover)
        
        # Add tools
        p.add_tools(CrosshairTool())
        p.add_tools(PanTool())
        p.add_tools(WheelZoomTool())
        p.add_tools(ResetTool())
        
        # Add restart markers if they exist
        if restart_headers:
            for restart_time in restart_headers:
                if isinstance(restart_time, list) and len(restart_time) > 0:
                    for rt in restart_time[0] if isinstance(restart_time[0], list) else [restart_time[0]]:
                        vline = Span(
                            location=rt,
                            dimension='height',
                            line_color='red',
                            line_dash='dashed',
                            line_width=2
                        )
                        p.add_layout(vline)
        
        # Format datetime axis
        p.xaxis.formatter = DatetimeTickFormatter(
            hours="%H:%M",
            days="%Y-%m-%d",
            months="%Y-%m",
            years="%Y",
        )
        
        # Style
        p.title.text_font_size = '14pt'
        p.xaxis.axis_label_text_font_size = '12pt'
        p.yaxis.axis_label_text_font_size = '12pt'
        
        # Display chart using HTML embedding
        html = file_html(p, CDN, f"{title} - {prop}")
        components.html(html, height=600, scrolling=True)
        
        render_time = time.perf_counter() - render_start
        
        st.success(f"⚡ Chart rendered in **{render_time*1000:.0f}ms**")
        
        # Export note
        st.info("💡 **Bokeh charts can be exported** using the toolbar icons above (save, pan, zoom, reset)")
    
    with tab2:
        st.markdown("### 🎯 Performance Comparison")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Bokeh Advantages")
            st.markdown("""
            - **Exceptional large dataset performance**: Handles 100k+ points smoothly
            - **Server-side rendering**: BokehJS handles rendering in browser efficiently
            - **Rich toolset**: Built-in pan, zoom, hover, crosshair, reset tools
            - **WebGL support**: Hardware-accelerated rendering for very large datasets
            - **Streaming data**: Built-in support for real-time data updates
            - **Customizable**: Highly flexible styling and interactions
            - **Export-ready**: Built-in save tool in toolbar
            """)
        
        with col2:
            st.markdown("#### Current Dataset Info")
            st.markdown(f"""
            - **Total rows**: {len(df_chart):,}
            - **Metric**: {prop}
            - **Time range**: {df_chart['date'].min()} to {df_chart['date'].max()}
            - **Render time**: {render_time*1000:.0f}ms
            """)
        
        st.markdown("---")
        st.markdown("#### Framework Comparison")
        
        comparison_data = {
            "Feature": ["Rendering Speed", "Browser Memory", "Large Datasets (>10k)", "Large Datasets (>100k)", "Interactivity", "Built-in Tools", "Export Options", "Declarative API", "Streaming Data"],
            "Bokeh": ["⚡ Very Fast", "✅ Low", "⚡ Excellent", "⚡ Excellent", "⚡ Rich toolset", "✅ Yes", "✅ Built-in", "❌ Imperative", "✅ Yes"],
            "Plotly": ["⚡ Fast", "✅ Low", "⚡ Excellent", "✅ Good", "⚡ Native", "✅ Yes", "✅ Multiple", "❌ Imperative", "⚠️ Limited"],
            "Altair": ["⏱️ Slower", "⚠️ Higher", "⚠️ Challenging", "❌ Poor", "✅ Good", "⚠️ Limited", "⚠️ Limited", "✅ Yes", "❌ No"],
        }
        st.table(comparison_data)
        
        st.info("""
        **Recommendation**: Bokeh is excellent for SAR file analysis when:
        - Working with very large datasets (>50k rows regularly)
        - Need rich interactive tools (pan, zoom, hover, crosshair)
        - Want built-in export functionality
        - Building dashboards with streaming or real-time data
        """)
    
    with tab3:
        st.markdown(f"### Dataset: {title} - {prop}")
        st.dataframe(df_chart, use_container_width=True)
        
        st.markdown("### Statistics")
        st.dataframe(df_chart[[prop]].describe())
