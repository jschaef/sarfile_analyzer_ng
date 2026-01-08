#!/usr/bin/python3
"""
Bokeh Charts Module - High-performance chart generation using Bokeh
Similar to alt.py but uses Bokeh for better performance with large datasets
"""
import time
import pandas as pd
from math import pi
from bokeh.plotting import figure
from bokeh.models import (
    HoverTool,
    Span,
    Label,
    ColumnDataSource,
    NumeralTickFormatter,
    CrosshairTool,
    DatetimeTickFormatter,
    Range1d,
)
from bokeh.embed import components
from bokeh.resources import CDN
import dataframe_funcs_pl as ddf

my_tz = time.tzname[0]


def _cdn_resources_html() -> str:
    cdn_js = CDN.js_files
    cdn_css = CDN.css_files
    parts: list[str] = []
    for css in cdn_css:
        parts.append(f'<link href="{css}" rel="stylesheet" type="text/css">')
    for js in cdn_js:
        parts.append(f'<script src="{js}"></script>')
    return "\n".join(parts) + ("\n" if parts else "")


_BOKEH_RESOURCES_HTML = _cdn_resources_html()


def sample_dataframe_for_viz(df, max_rows=5000):
    """Sample large dataframes to reduce memory usage during visualization."""
    if len(df) > max_rows:
        return df.sample(n=max_rows).sort_index()
    return df


def parse_restart_times(restart_headers, os_details):
    """Parse restart header strings to datetime objects.
    
    Args:
        restart_headers: List of strings like ["Linux restart 14:23:45"]
        os_details: OS details dict containing date information
    
    Returns:
        List of datetime objects in UTC
    """
    restart_times = []
    if not restart_headers:
        return restart_times
    
    for header in restart_headers:
        # Extract time from string like "Linux restart 14:23:45"
        xval = header.split()[-1]
        date_str, _ = ddf.format_date(os_details)
        z = pd.to_datetime(f"{date_str} {xval}", format="mixed")
        z = z.replace(tzinfo=None).replace(tzinfo=pd.Timestamp('2000-01-01', tz='UTC').tzinfo)
        restart_times.append(z)
    
    return restart_times


def _restart_label_flags(
    times,
    x_min,
    x_max,
    plot_width_px: int | None,
    min_sep_px: int = 18,
):
    """Return a list of booleans whether to show the RESTART label.

    Always draws dashed lines. Labels are suppressed if neighboring restart lines
    are too close in x such that text would overlap.

    We approximate overlap by converting a pixel separation threshold into a
    time delta using the current x-span and plot width.
    """
    if not times:
        return []
    if x_min is None or x_max is None or plot_width_px is None or plot_width_px <= 0:
        return [True] * len(times)

    try:
        span = pd.Timestamp(x_max) - pd.Timestamp(x_min)
        if span <= pd.Timedelta(0):
            return [True] * len(times)
        min_dt = span * (min_sep_px / float(plot_width_px))
    except Exception:
        return [True] * len(times)

    flags = []
    last_labeled = None
    for t in times:
        if last_labeled is None:
            flags.append(True)
            last_labeled = t
            continue
        try:
            if (pd.Timestamp(t) - pd.Timestamp(last_labeled)) >= min_dt:
                flags.append(True)
                last_labeled = t
            else:
                flags.append(False)
        except Exception:
            flags.append(True)
            last_labeled = t
    return flags


def _scope_hover_to_renderers(hover_tool: HoverTool, renderers):
    """Limit a HoverTool to a specific set of glyph renderers."""
    try:
        hover_tool.renderers = list(renderers) if renderers is not None else []
    except Exception:
        pass


def _ensure_restart_hover_tool(p):
    """Create (or reuse) a restart-only hover tool for a figure.

    Important: The metric hover tool(s) must be scoped to their own renderers,
    otherwise a wide restart hit target can prevent metric tooltips.
    """
    tool = getattr(p, "_restart_hover_tool", None)
    if tool is None:
        tool = HoverTool(
            tooltips=[("RESTART", "@restart_time{%H:%M:%S}")],
            formatters={"@restart_time": "datetime"},
            mode="mouse",
        )
        tool.renderers = []
        p.add_tools(tool)
        p._restart_hover_tool = tool
    return tool


def _add_restart_marker(
    p,
    x,
    color: str = "orange",
    y_mid: float | None = None,
    show_label: bool = True,
    restart_hover: HoverTool | None = None,
    y_low: float | None = None,
    y_high: float | None = None,
):
    # Always draw the dashed line.
    p.add_layout(
        Span(
            location=x,
            dimension="height",
            line_color=color,
            line_dash="dashed",
            line_width=2,
        )
    )

    # Add a thin, nearly invisible but hoverable glyph at the same x.
    # (Annotations like Span can't be hit-tested by HoverTool.)
    if restart_hover is not None:
        try:
            if y_low is None or y_high is None:
                y_low = getattr(getattr(p, "y_range", None), "start", None)
                y_high = getattr(getattr(p, "y_range", None), "end", None)
            if y_low is None or y_high is None:
                y_low, y_high = 0.0, 1.0

            restart_src = ColumnDataSource(
                {
                    "x0": [x],
                    "x1": [x],
                    "y0": [float(y_low)],
                    "y1": [float(y_high)],
                    "restart_time": [x],
                }
            )
            restart_r = p.segment(
                x0="x0",
                y0="y0",
                x1="x1",
                y1="y1",
                source=restart_src,
                line_color=color,
                line_alpha=0.001,
                line_width=8,
            )
            if restart_hover.renderers is None:
                restart_hover.renderers = []
            restart_hover.renderers.append(restart_r)
        except Exception:
            pass

    if not show_label:
        return

    # Place label in *data space* so it's centered in the plotting area
    # (not affected by title/toolbar/axis padding).
    if y_mid is None:
        try:
            y_start = getattr(p.y_range, "start", None)
            y_end = getattr(p.y_range, "end", None)
            if y_start is not None and y_end is not None:
                y_mid = (float(y_start) + float(y_end)) / 2.0
        except Exception:
            y_mid = None

    if y_mid is None:
        y_mid = 0.0

    p.add_layout(
        Label(
            x=x,
            y=y_mid,
            x_units="data",
            y_units="data",
            x_offset=8,
            text="RESTART",
            angle=pi / 2,
            text_color=color,
            text_font_size="10pt",
            text_font_style="bold",
            text_align="center",
            text_baseline="middle",
        )
    )


def draw_single_chart_v1(
    df,
    property,
    restart_headers,
    os_details,
    width,
    hight,
    ylabelpadd=10,
    font_size=None,
    title=None,
):
    """
    Create a Bokeh chart for single metric visualization.
    Returns tuple: (HTML string for rendering via components.html(), figure object for PDF export)
    """
    def _tooltip_field(field_name: str) -> str:
        # Sar metrics often contain special characters (e.g. "ldavg-15").
        # Bokeh tooltips require @{field} syntax for such names.
        return f"@{{{field_name}}}"

    # Compute y-range from full (unsampled) data to avoid surprising scaling.
    # Also coerce to numeric to ignore non-numeric artifacts.
    y_series_full = pd.to_numeric(df.get(property), errors="coerce")
    y_min = y_series_full.min(skipna=True)
    y_max = y_series_full.max(skipna=True)

    # Sample large datasets to reduce memory usage
    df = sample_dataframe_for_viz(df, max_rows=5000)
    df["date_utc"] = df["date"].dt.tz_localize("UTC")
    
    if "metric" in df.columns:
        color_item = "metric"
    else:
        color_item = "file"
    
    # Create Bokeh figure
    p = figure(
        title=title or f"{property}",
        x_axis_label='Time',
        y_axis_label=property,
        x_axis_type='datetime',
        width=width,
        height=hight,
        toolbar_location="above",
    )

    # Stabilize y-axis: Bokeh's automatic DataRange can look "too high" for small float ranges.
    # Explicitly set a padded range from the data.
    if pd.notna(y_min) and pd.notna(y_max):
        span = float(y_max - y_min)
        if span == 0.0:
            pad = max(abs(float(y_max)) * 0.1, 1.0)
        else:
            pad = span * 0.1
        start = float(y_min) - pad
        end = float(y_max) + pad
        if float(y_min) >= 0.0:
            start = max(0.0, start)
        p.y_range = Range1d(start=start, end=end)
    
    # Group by color_item and plot lines for each group
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
    legend_items = []
    
    metric_renderers = []
    for i, (name, group) in enumerate(df.groupby(color_item)):
        color = colors[i % len(colors)]
        # Create ColumnDataSource with only the columns we need
        source_data = {
            'date_utc': group['date_utc'].values,
            property: group[property].values,
            color_item: [name] * len(group)
        }
        source = ColumnDataSource(data=source_data)
        
        line = p.line(
            x='date_utc',
            y=property,
            source=source,
            line_width=2,
            color=color,
            alpha=0.8,
            legend_label=str(name)
        )
        metric_renderers.append(line)
        legend_items.append((str(name), [line]))
    
    # Add hover tool
    hover = HoverTool(
        tooltips=[
            ('Time', '@date_utc{%F %T}'),
            (property, f"{_tooltip_field(property)}{{0.00}}"),
            (color_item.capitalize(), _tooltip_field(color_item)),
        ],
        formatters={'@date_utc': 'datetime'},
        mode='vline'
    )
    p.add_tools(hover)
    _scope_hover_to_renderers(hover, metric_renderers)
    
    # Add crosshair tool for mouse following lines
    p.add_tools(CrosshairTool())
    
    # Add restart markers if they exist
    restart_times = parse_restart_times(restart_headers, os_details)
    restart_hover = _ensure_restart_hover_tool(p) if restart_times else None
    try:
        x_min = df["date_utc"].min()
        x_max = df["date_utc"].max()
    except Exception:
        x_min, x_max = None, None
    try:
        y_mid = (float(y_min) + float(y_max)) / 2.0 if pd.notna(y_min) and pd.notna(y_max) else None
    except Exception:
        y_mid = None
    show_flags = _restart_label_flags(sorted(restart_times), x_min, x_max, getattr(p, "width", None))
    for restart_time, show_label in zip(sorted(restart_times), show_flags):
        _add_restart_marker(
            p,
            restart_time,
            color="orange",
            y_mid=y_mid,
            show_label=show_label,
            restart_hover=restart_hover,
            y_low=getattr(getattr(p, "y_range", None), "start", None),
            y_high=getattr(getattr(p, "y_range", None), "end", None),
        )
    
    # Configure legend
    if legend_items:
        p.legend.location = "top_right"
        p.legend.click_policy = "hide"
    
    # Format Y-axis to show decimal notation instead of scientific notation
    p.yaxis.formatter = NumeralTickFormatter(format="0,0.00")
    
    # Apply font sizes if specified
    if font_size is not None:
        if p.title:
            p.title.text_font_size = f'{font_size}pt'
        p.xaxis.axis_label_text_font_size = f'{font_size}pt'
        p.yaxis.axis_label_text_font_size = f'{font_size}pt'
        p.xaxis.major_label_text_font_size = f'{font_size}pt'
        p.yaxis.major_label_text_font_size = f'{font_size}pt'
    
    # Return HTML string and figure object (for PDF export)
    script, div = components(p)
    # Include Bokeh CDN resources for proper rendering
    cdn_js = CDN.js_files
    cdn_css = CDN.css_files
    resources_html = ""
    for css in cdn_css:
        resources_html += f'<link href="{css}" rel="stylesheet" type="text/css">\n'
    for js in cdn_js:
        resources_html += f'<script src="{js}"></script>\n'
    
    full_html = f"{resources_html}{script}\n{div}"
    return full_html, p


def overview_v1(
    df, restart_headers, os_details, font_size=None, width=None, height=None, title=None
):
    """
    Create a Bokeh multi-metric overview chart with clickable legend.
    Supports both melted (long) and wide DataFrames.
    Returns tuple: (HTML string for rendering via components.html(), figure object for PDF export)
    """
    # Sample large datasets to reduce memory usage
    df = sample_dataframe_for_viz(df, max_rows=5000)
    
    # Create Bokeh figure
    p = figure(
        title=title or "Metrics Overview",
        x_axis_label='Time',
        y_axis_label='Value',
        x_axis_type='datetime',
        width=width,
        height=height,
        toolbar_location="above",
    )
    
    # Detect if DF is wide or long
    is_long = 'metrics' in df.columns and 'y' in df.columns
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    metric_renderers = []

    if is_long:
        # Long format: metrics in 'metrics' column, values in 'y' column
        metrics = df['metrics'].unique()
        try:
            grouped = df.sort_values('date').groupby('metrics', sort=False)
        except TypeError:
            grouped = df.sort_values('date').groupby('metrics')

        metric_to_color = {m: colors[i % len(colors)] for i, m in enumerate(metrics)}
        
        for metric, metric_df in grouped:
            source = ColumnDataSource(data={'date': metric_df['date'].values, 'y': metric_df['y'].values})
            line = p.line(x='date', y='y', source=source, line_width=2, color=metric_to_color[metric], 
                         alpha=0.8, legend_label=str(metric), name=str(metric))
            metric_renderers.append(line)
        y_vals = df['y']
    else:
        # Wide format: Columns are metrics, index (or 'date' column) is time
        if 'date' in df.columns:
            x_data = df['date'].values
            metrics = [c for c in df.columns if c != 'date']
        else:
            x_data = df.index.values
            metrics = df.columns
            
        for i, metric in enumerate(metrics):
            source = ColumnDataSource(data={'date': x_data, 'y': df[metric].values})
            line = p.line(x='date', y='y', source=source, line_width=2, color=colors[i % len(colors)], 
                         alpha=0.8, legend_label=str(metric), name=str(metric))
            metric_renderers.append(line)
        y_vals = df[metrics]

    # Precompute y-range once (used for restart markers)
    try:
        if is_long:
             y_low = float(pd.to_numeric(y_vals, errors='coerce').min(skipna=True))
             y_high = float(pd.to_numeric(y_vals, errors='coerce').max(skipna=True))
        else:
             y_low = float(y_vals.min().min())
             y_high = float(y_vals.max().max())
    except Exception:
        y_low, y_high = None, None

        line = p.line(
            x='date',
            y='y',
            source=source,
            line_width=2,
            color=color,
            alpha=0.8,
            legend_label=str(metric),
            name=str(metric),
        )
        metric_renderers.append(line)
    
    # Add hover tool
    hover = HoverTool(
        tooltips=[
            ('Time', '@date{%F %T}'),
            ('Value', '@y{0.00}'),
            ('Metric', '$name'),
        ],
        formatters={'@date': 'datetime'},
        mode='vline'
    )
    p.add_tools(hover)
    _scope_hover_to_renderers(hover, metric_renderers)
    
    # Add crosshair tool
    p.add_tools(CrosshairTool())
    
    # Add restart markers if they exist
    restart_times = parse_restart_times(restart_headers, os_details)
    # Keep restart timestamps comparable to the (typically tz-naive) df['date'].
    try:
        restart_times = [pd.Timestamp(t).tz_localize(None) for t in restart_times]
    except Exception:
        pass
    restart_hover = _ensure_restart_hover_tool(p) if restart_times else None
    try:
        x_min = df["date"].min()
        x_max = df["date"].max()
    except Exception:
        x_min, x_max = None, None
    try:
        y_mid = (float(y_low) + float(y_high)) / 2.0 if y_low is not None and y_high is not None else None
    except Exception:
        y_mid = None
    show_flags = _restart_label_flags(sorted(restart_times), x_min, x_max, getattr(p, "width", None))
    for restart_time, show_label in zip(sorted(restart_times), show_flags):
        _add_restart_marker(
            p,
            restart_time,
            color="orange",
            y_mid=y_mid,
            show_label=show_label,
            restart_hover=restart_hover,
            y_low=y_low,
            y_high=y_high,
        )
    
    # Configure legend
    p.legend.location = "top_right"
    p.legend.click_policy = "hide"  # Click legend to hide/show lines
    
    # Format Y-axis to show decimal notation
    p.yaxis.formatter = NumeralTickFormatter(format="0,0.00")
    
    # Apply font sizes if specified
    if font_size is not None:
        if p.title:
            p.title.text_font_size = f'{font_size}pt'
        p.xaxis.axis_label_text_font_size = f'{font_size}pt'
        p.yaxis.axis_label_text_font_size = f'{font_size}pt'
        p.xaxis.major_label_text_font_size = f'{font_size}pt'
        p.yaxis.major_label_text_font_size = f'{font_size}pt'
    
    # Return HTML components and figure object (for PDF export)
    script, div = components(p)
    full_html = f"{_BOKEH_RESOURCES_HTML}{script}\n{div}"
    return full_html, p


def overview_v3(
    collect_field, reboot_headers, width, height, lsel, font_size, title=None
):
    """
    Create a Bokeh multi-file comparison chart with clickable legend.
    Compares same metric across multiple files.
    Returns tuple: (HTML string, figure object)
    """
    import pandas as pd

    def _tooltip_field(field_name: str) -> str:
        # Metric names can contain characters like '%' or '-' (e.g. "%usr", "ldavg-1").
        # Bokeh hover needs @{field} syntax in that case.
        return f"@{{{field_name}}}"
    
    color_item = lsel  # Usually "file"
    b_df = pd.DataFrame()
    
    # Collect all dataframes
    for data in collect_field:
        df = data[0]
        df = sample_dataframe_for_viz(df, max_rows=5000)
        if not df.empty:
            df["date_utc"] = df["date"].dt.tz_localize("UTC")
            b_df = pd.concat([b_df, df], ignore_index=False)
    
    if b_df.empty:
        return "", None
    
    property = collect_field[0][1]  # Metric name
    
    # Create Bokeh figure
    p = figure(
        title=title or f"{property} Comparison",
        x_axis_label='Time',
        y_axis_label=property,
        x_axis_type='datetime',
        width=width,
        height=height,
        toolbar_location="above",
    )
    
    # Get unique files
    files = b_df[color_item].unique()
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    # Plot lines for each file
    metric_renderers = []
    for i, file in enumerate(files):
        file_df = b_df[b_df[color_item] == file]
        color = colors[i % len(colors)]
        
        source_data = {
            'date_utc': file_df['date_utc'].values,
            property: file_df[property].values,
            color_item: [file] * len(file_df)
        }
        source = ColumnDataSource(data=source_data)
        
        line = p.line(
            x='date_utc',
            y=property,
            source=source,
            line_width=2,
            color=color,
            alpha=0.8,
            legend_label=str(file)
        )
        metric_renderers.append(line)
    
    # Add hover tool
    hover = HoverTool(
        tooltips=[
            ('Time of Day', '@date_utc{%H:%M:%S}'),
            (property, f"{_tooltip_field(property)}{{0.00}}"),
        ],
        formatters={'@date_utc': 'datetime'},
        mode='vline'
    )
    p.add_tools(hover)
    _scope_hover_to_renderers(hover, metric_renderers)
    p.add_tools(CrosshairTool())
    
    # Add restart markers if they exist - match restarts to files
    if reboot_headers:
        restart_hover = _ensure_restart_hover_tool(p)
        try:
            y_low = float(b_df[property].min())
            y_high = float(b_df[property].max())
        except Exception:
            y_low, y_high = None, None
        for header in reboot_headers:
            if header[0]:
                # Extract hostname and date from os_details to match with filename
                hostname = header[1].split()[2].strip("()")
                date = header[1].split()[3]
                
                # Find which file this restart belongs to
                for file in files:
                    if hostname in file and date in file:
                        # Parse restart times for this file
                        restart_times = parse_restart_times(header[0], header[1])
                        try:
                            x_min = b_df["date_utc"].min()
                            x_max = b_df["date_utc"].max()
                        except Exception:
                            x_min, x_max = None, None
                        try:
                            y_mid = (float(b_df[property].min()) + float(b_df[property].max())) / 2.0
                        except Exception:
                            y_mid = None
                        show_flags = _restart_label_flags(sorted(restart_times), x_min, x_max, getattr(p, "width", None))
                        for restart_time, show_label in zip(sorted(restart_times), show_flags):
                            _add_restart_marker(
                                p,
                                restart_time,
                                color="orange",
                                y_mid=y_mid,
                                show_label=show_label,
                                restart_hover=restart_hover,
                                y_low=y_low,
                                y_high=y_high,
                            )
                        break
    
    # Configure legend
    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    
    # Format Y-axis
    p.yaxis.formatter = NumeralTickFormatter(format="0,0.00")
    
    # Apply font sizes if specified
    if font_size is not None:
        if p.title:
            p.title.text_font_size = f'{font_size}pt'
        p.xaxis.axis_label_text_font_size = f'{font_size}pt'
        p.yaxis.axis_label_text_font_size = f'{font_size}pt'
        p.xaxis.major_label_text_font_size = f'{font_size}pt'
        p.yaxis.major_label_text_font_size = f'{font_size}pt'
    
    # Return HTML components and figure object (for PDF export)
    script, div = components(p)
    # Include Bokeh CDN resources for proper rendering
    cdn_js = CDN.js_files
    cdn_css = CDN.css_files
    resources_html = ""
    for css in cdn_css:
        resources_html += f'<link href="{css}" rel="stylesheet" type="text/css">\n'
    for js in cdn_js:
        resources_html += f'<script src="{js}"></script>\n'
    
    full_html = f"{resources_html}{script}\n{div}"
    return full_html, p


def overview_v6(collect_field, reboot_headers, width, height, font_size, title=None):
    """Create a Bokeh chart that overlays multiple days onto a single 24h window."""
    def _tooltip_field(field_name: str) -> str:
        # Metric names can contain characters like '%' or '-' (e.g. "%usr", "ldavg-1").
        # Bokeh hover needs @{field} syntax in that case.
        return f"@{{{field_name}}}"

    color_item = "date_short"
    b_df = pd.DataFrame()

    # Collect and normalize data from all selected days
    for data in collect_field:
        df = data[0]
        df = sample_dataframe_for_viz(df, max_rows=5000)
        if df.empty:
            continue
        df["date_utc"] = df["date"].dt.tz_localize("UTC")
        b_df = pd.concat([b_df, df], ignore_index=False)

    if b_df.empty:
        return "", None

    property = collect_field[0][1]
    b_df["date_short"] = b_df["date"].dt.floor("1D")

    # Align all timestamps to the same reference day while preserving time-of-day
    normalized = b_df["date_utc"].dt.normalize()
    base_date = normalized.min()
    aligned_series = base_date + (b_df["date_utc"] - normalized)
    b_df["aligned_time"] = aligned_series.dt.tz_localize(None)
    b_df["original_time"] = b_df["date_utc"].dt.tz_localize(None)

    # Create figure that shows a single 24-hour window
    p = figure(
        title=title or f"{property} Daily Overlay",
        x_axis_label="Time of Day (UTC)",
        y_axis_label=property,
        x_axis_type="datetime",
        width=width,
        height=height,
        toolbar_location="above",
    )

    p.xaxis.formatter = DatetimeTickFormatter(
        hours="%H:%M",
        minutes="%H:%M",
        hourmin="%H:%M",
    )

    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    date_color_map = {}

    # Plot each day as a separate line but aligned to the common time axis
    metric_renderers = []
    for i, date in enumerate(sorted(b_df[color_item].unique())):
        date_df = b_df[b_df[color_item] == date]
        color = colors[i % len(colors)]
        date_label = pd.Timestamp(date).strftime('%Y-%m-%d')
        date_color_map[date_label] = color

        source_data = {
            'aligned_time': date_df['aligned_time'].values,
            property: date_df[property].values,
            'date_label': [date_label] * len(date_df),
            'original_time': date_df['original_time'].values,
        }
        source = ColumnDataSource(data=source_data)

        line = p.line(
            x='aligned_time',
            y=property,
            source=source,
            line_width=2,
            color=color,
            alpha=0.85,
            legend_label=date_label,
        )
        metric_renderers.append(line)

    hover = HoverTool(
        tooltips=[
            ('Time of Day', '@aligned_time{%H:%M:%S}'),
            (property, f"{_tooltip_field(property)}{{0.00}}"),
        ],
        formatters={
            '@aligned_time': 'datetime',
        },
        mode='vline'
    )
    p.add_tools(hover)
    _scope_hover_to_renderers(hover, metric_renderers)
    p.add_tools(CrosshairTool())

    # Add restart markers (aligned to base day)
    if reboot_headers:
        restart_hover = _ensure_restart_hover_tool(p)
        # Determine x span on the aligned axis for label suppression.
        try:
            x_min = b_df["aligned_time"].min()
            x_max = b_df["aligned_time"].max()
        except Exception:
            x_min, x_max = None, None
        try:
            y_mid = (float(b_df[property].min()) + float(b_df[property].max())) / 2.0
        except Exception:
            y_mid = None
        try:
            y_low = float(b_df[property].min())
            y_high = float(b_df[property].max())
        except Exception:
            y_low, y_high = None, None

        for header in reboot_headers:
            if not header[0]:
                continue
            date_str, date_format = ddf.format_date(header[1])
            parsed_date = pd.to_datetime(date_str, format=date_format, errors='coerce')
            if pd.isna(parsed_date):
                parsed_date = pd.to_datetime(date_str, errors='coerce')
            date_label = parsed_date.strftime('%Y-%m-%d') if parsed_date is not None and not pd.isna(parsed_date) else str(date_str)
            restart_times = parse_restart_times(header[0], header[1])
            aligned_times = []
            for restart_time in restart_times:
                restart_ts = pd.Timestamp(restart_time)
                if restart_ts.tzinfo is None:
                    restart_ts = restart_ts.tz_localize('UTC')
                aligned_restart = (base_date + (restart_ts - restart_ts.normalize())).tz_localize(None)
                aligned_times.append(aligned_restart)

            show_flags = _restart_label_flags(sorted(aligned_times), x_min, x_max, getattr(p, "width", None))
            for aligned_restart, show_label in zip(sorted(aligned_times), show_flags):
                _add_restart_marker(
                    p,
                    aligned_restart,
                    color=date_color_map.get(date_label, 'orange'),
                    y_mid=y_mid,
                    show_label=show_label,
                    restart_hover=restart_hover,
                    y_low=y_low,
                    y_high=y_high,
                )

    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    p.yaxis.formatter = NumeralTickFormatter(format="0,0.00")

    if font_size is not None:
        if p.title:
            p.title.text_font_size = f'{font_size}pt'
        p.xaxis.axis_label_text_font_size = f'{font_size}pt'
        p.yaxis.axis_label_text_font_size = f'{font_size}pt'
        p.xaxis.major_label_text_font_size = f'{font_size}pt'
        p.yaxis.major_label_text_font_size = f'{font_size}pt'

    # Return HTML components and figure object (for PDF export)
    script, div = components(p)
    cdn_js = CDN.js_files
    cdn_css = CDN.css_files
    resources_html = ""
    for css in cdn_css:
        resources_html += f'<link href="{css}" rel="stylesheet" type="text/css">\n'
    for js in cdn_js:
        resources_html += f'<script src="{js}"></script>\n'
    full_html = f"{resources_html}{script}\n{div}"
    return full_html, p


def overview_v5(
    b_df,
    property,
    filename,
    reboot_headers,
    width,
    height,
    lsel,
    font_size,
    os_details,
    title=None,
):
    """Create a Bokeh chart for one file, many devices.

    This mirrors the intent of alt.overview_v5 used by display_multi.show_multi:
    plot the same metric for multiple sub-devices (e.g. CPUs) over time.
    """

    def _tooltip_field(field_name: str) -> str:
        # Metric names can include characters like '%' or '-' (e.g. "%usr", "ldavg-1").
        return f"@{{{field_name}}}"

    if b_df is None or len(b_df) == 0:
        return "", None

    # Normalize restart headers input shape.
    restart_headers = reboot_headers
    if isinstance(restart_headers, list) and restart_headers and isinstance(restart_headers[0], list):
        restart_headers = restart_headers[0]

    # Compute y-range from full data (before sampling).
    y_series_full = pd.to_numeric(b_df.get(property), errors="coerce")
    y_min = y_series_full.min(skipna=True)
    y_max = y_series_full.max(skipna=True)

    b_df = sample_dataframe_for_viz(b_df, max_rows=5000)
    if "date" not in b_df.columns:
        return "", None

    # Ensure datetime and add UTC column.
    b_df = b_df.copy()
    b_df["date"] = pd.to_datetime(b_df["date"], errors="coerce")
    b_df["date_utc"] = b_df["date"].dt.tz_localize("UTC")

    color_item = lsel  # typically 'sub_device'

    p = figure(
        title=title or f"{property}",
        x_axis_label="Time",
        y_axis_label=property,
        x_axis_type="datetime",
        width=width,
        height=height,
        toolbar_location="above",
    )

    # Stabilize y-axis range.
    if pd.notna(y_min) and pd.notna(y_max):
        span = float(y_max - y_min)
        pad = max(abs(float(y_max)) * 0.1, 1.0) if span == 0.0 else span * 0.1
        start = float(y_min) - pad
        end = float(y_max) + pad
        if float(y_min) >= 0.0:
            start = max(0.0, start)
        p.y_range = Range1d(start=start, end=end)

    # Plot each device as a separate line.
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    groups = []
    if color_item in b_df.columns:
        groups = list(pd.unique(b_df[color_item]))
    else:
        groups = [filename]
        b_df[color_item] = filename

    metric_renderers = []
    for i, group_name in enumerate(groups):
        gdf = b_df[b_df[color_item] == group_name]
        if gdf.empty:
            continue
        color = colors[i % len(colors)]
        source = ColumnDataSource(
            data={
                "date_utc": gdf["date_utc"].values,
                property: gdf[property].values,
                color_item: [group_name] * len(gdf),
            }
        )
        line = p.line(
            x="date_utc",
            y=property,
            source=source,
            line_width=2,
            color=color,
            alpha=0.85,
            legend_label=str(group_name),
        )
        metric_renderers.append(line)

    hover = HoverTool(
        tooltips=[
            ("Time", "@date_utc{%F %T}"),
            (property, f"{_tooltip_field(property)}{{0.00}}"),
            (color_item, _tooltip_field(color_item)),
        ],
        formatters={"@date_utc": "datetime"},
        mode="vline",
    )
    p.add_tools(hover)
    _scope_hover_to_renderers(hover, metric_renderers)
    p.add_tools(CrosshairTool())

    # Add restart markers.
    restart_times = parse_restart_times(restart_headers, os_details)
    restart_hover = _ensure_restart_hover_tool(p) if restart_times else None
    try:
        x_min = b_df["date_utc"].min()
        x_max = b_df["date_utc"].max()
    except Exception:
        x_min, x_max = None, None
    try:
        y_mid = (float(y_min) + float(y_max)) / 2.0 if pd.notna(y_min) and pd.notna(y_max) else None
    except Exception:
        y_mid = None
    show_flags = _restart_label_flags(sorted(restart_times), x_min, x_max, getattr(p, "width", None))
    for restart_time, show_label in zip(sorted(restart_times), show_flags):
        _add_restart_marker(
            p,
            restart_time,
            color="orange",
            y_mid=y_mid,
            show_label=show_label,
            restart_hover=restart_hover,
            y_low=getattr(getattr(p, "y_range", None), "start", None),
            y_high=getattr(getattr(p, "y_range", None), "end", None),
        )

    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    p.yaxis.formatter = NumeralTickFormatter(format="0,0.00")

    if font_size is not None:
        if p.title:
            p.title.text_font_size = f"{font_size}pt"
        p.xaxis.axis_label_text_font_size = f"{font_size}pt"
        p.yaxis.axis_label_text_font_size = f"{font_size}pt"
        p.xaxis.major_label_text_font_size = f"{font_size}pt"
        p.yaxis.major_label_text_font_size = f"{font_size}pt"

    script, div = components(p)
    cdn_js = CDN.js_files
    cdn_css = CDN.css_files
    resources_html = ""
    for css in cdn_css:
        resources_html += f'<link href="{css}" rel="stylesheet" type="text/css">\n'
    for js in cdn_js:
        resources_html += f'<script src="{js}"></script>\n'
    full_html = f"{resources_html}{script}\n{div}"
    return full_html, p

    # Return HTML components and figure object (for PDF export)
    script, div = components(p)
    # Include Bokeh CDN resources for proper rendering
    cdn_js = CDN.js_files
    cdn_css = CDN.css_files
    resources_html = ""
    for css in cdn_css:
        resources_html += f'<link href="{css}" rel="stylesheet" type="text/css">\n'
    for js in cdn_js:
        resources_html += f'<script src="{js}"></script>\n'
    
    full_html = f"{resources_html}{script}\n{div}"
    return full_html, p

