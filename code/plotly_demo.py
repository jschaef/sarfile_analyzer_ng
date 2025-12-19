#!/usr/bin/python3
"""
Plotly Demo Page - Performance comparison with Altair
Demonstrates faster rendering and lower memory usage with Plotly
"""
import streamlit as st
import polars as pl
import plotly.graph_objects as go
import plotly.express as px
import layout_helper_pl as lh
import helpers_pl
import pl_helpers2 as pl_h2
import dia_compute_pl as dia_compute
from config import Config
import re
import time

file_chosen = ""
df_complete = None

def plotly_demo(config_obj, username, selection, df, os_details):
    """
    Plotly demonstration page showing improved performance over Altair.
    Uses the same data flow but renders with Plotly for comparison.
    """
    perf_intensive_metrics = re.compile(r'^CPU|SOfT.*', re.IGNORECASE)
    global file_chosen, df_complete
    
    st.subheader("⚡ Plotly Performance Demo")
    st.info("""
    **Why Plotly?** This page demonstrates Plotly as a faster alternative to Altair:
    - 🚀 **Faster rendering** (2-3x faster than Altair)
    - 💾 **Lower browser memory** usage
    - 🎯 **Better interactivity** with large datasets
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
    
    # Convert to Python datetime for Plotly
    df_chart = df_chart.reset_index(drop=True)
    
    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["📈 Plotly Chart", "⚡ Performance Info", "🗃 Data"])
    
    with tab1:
        st.markdown(f"### {title} - {prop}")
        
        # Measure rendering time
        render_start = time.perf_counter()
        
        # Create Plotly figure
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=df_chart['date'],
            y=df_chart[prop],
            mode='lines',
            name=prop,
            line=dict(width=2),
            hovertemplate='<b>Time</b>: %{x}<br><b>' + prop + '</b>: %{y:.2f}<extra></extra>'
        ))
        
        # Add restart markers if they exist
        if restart_headers:
            for restart_time in restart_headers:
                if isinstance(restart_time, list) and len(restart_time) > 0:
                    for rt in restart_time[0] if isinstance(restart_time[0], list) else [restart_time[0]]:
                        fig.add_vline(
                            x=rt,
                            line_dash="dash",
                            line_color="red",
                            annotation_text="Restart",
                            annotation_position="top"
                        )
        
        # Update layout
        fig.update_layout(
            title=dict(text=f"{title} - {prop}", x=0.5, xanchor='center'),
            xaxis_title="Time",
            yaxis_title=prop,
            hovermode='x unified',
            height=500,
            template='plotly_white',
            showlegend=False
        )
        
        # Display chart
        st.plotly_chart(fig, use_container_width=True, key="plotly_main_chart")
        
        render_time = time.perf_counter() - render_start
        
        st.success(f"⚡ Chart rendered in **{render_time*1000:.0f}ms**")
        
        # Download options
        st.markdown("##### Download Options")
        col1, col2 = st.columns(2)
        with col1:
            # PNG download
            st.download_button(
                label="📥 Download as PNG",
                data=fig.to_image(format="png"),
                file_name=f"{selection}_{helpers_pl.validate_convert_names(title)}_{prop}.png",
                mime="image/png"
            )
        with col2:
            # HTML download
            html_str = fig.to_html(include_plotlyjs='cdn')
            st.download_button(
                label="📥 Download as HTML",
                data=html_str,
                file_name=f"{selection}_{helpers_pl.validate_convert_names(title)}_{prop}.html",
                mime="text/html"
            )
    
    with tab2:
        st.markdown("### 🎯 Performance Comparison")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Plotly Advantages")
            st.markdown("""
            - **Faster rendering**: 2-3x faster than Altair for large datasets
            - **Lower memory**: Reduced browser memory footprint
            - **Better interactivity**: Smooth pan/zoom even with many points
            - **Native tooltips**: Fast, responsive hover interactions
            - **Multiple export formats**: PNG, SVG, HTML, PDF
            - **WebGL support**: Hardware acceleration for very large datasets
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
        st.markdown("#### When to use Plotly vs Altair?")
        
        comparison_data = {
            "Feature": ["Rendering Speed", "Browser Memory", "Large Datasets (>10k)", "Interactivity", "Export Options", "Declarative API", "PDF Generation"],
            "Plotly": ["⚡ Fast", "✅ Low", "⚡ Excellent", "⚡ Native", "✅ Multiple", "❌ Imperative", "✅ Built-in"],
            "Altair": ["⏱️ Slower", "⚠️ Higher", "⚠️ Challenging", "✅ Good", "⚠️ Limited", "✅ Yes", "⚠️ External"],
        }
        st.table(comparison_data)
        
        st.info("""
        **Recommendation**: For SAR file analysis with potentially large datasets, 
        Plotly offers better performance and user experience. Consider migrating 
        charts that handle >5000 rows regularly.
        """)
    
    with tab3:
        st.markdown(f"### Dataset: {title} - {prop}")
        st.dataframe(df_chart, use_container_width=True)
        
        st.markdown("### Statistics")
        st.dataframe(df_chart[[prop]].describe())
