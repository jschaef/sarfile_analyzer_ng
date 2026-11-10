"""ECharts line charts for the Streamlit app (st.echarts_chart, Streamlit >= 1.64).

Drawn in the browser like the web frontend (sarfile_analyzer_web) does: no
Bokeh/Firefox round trip, LTTB sampling, zoom with the mouse wheel or the
slider. Each line gets its own dataset, so lines with different timestamps
(several files, devices) never break each other up. The PDF export keeps
using Bokeh or Altair.

st.echarts_chart takes JSON only - no JavaScript formatters, so labels use
ECharts' string templates.
"""

import pandas as pd
import streamlit as st

from bokeh_charts import parse_restart_times

# Bokeh's Category10, the palette of the other chart libraries in the app
PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]
RESTART_COLOR = "#d62728"


def _utc(values) -> pd.Series:
    """sar times are wall-clock times without zone; send them as UTC so the
    browser does not shift them into its own time zone (the chart uses UTC)."""
    series = pd.to_datetime(pd.Series(values))
    if series.dt.tz is None:
        series = series.dt.tz_localize("UTC")
    return series.dt.tz_convert("UTC")


def _line(name: str, dates, values) -> tuple[str, pd.DataFrame]:
    frame = pd.DataFrame({
        "date": _utc(list(dates)),
        "value": pd.to_numeric(pd.Series(list(values)), errors="coerce"),
    })
    return name, frame.sort_values("date", ignore_index=True)


def _restart_series(times, color: str) -> dict:
    """An empty, legend-less series that only carries dashed restart lines."""
    return {
        "type": "line",
        "name": "LINUX RESTART",
        "data": [],
        "silent": True,
        "tooltip": {"show": False},
        "markLine": {
            "symbol": "none",
            "silent": True,
            "lineStyle": {"color": color, "type": "dashed", "width": 1.5},
            "label": {"formatter": "LINUX RESTART", "color": color, "position": "insideEndTop"},
            "data": [{"xAxis": pd.Timestamp(t).isoformat()} for t in times],
        },
    }


def build_option(
    lines: list[tuple[str, pd.DataFrame]],
    restarts: list[tuple[list, str]] | None = None,
    title: str | None = None,
    y_name: str | None = None,
    font_size: int | None = None,
    x_format: str = "{HH}:{mm}",
) -> dict:
    """lines: [(name, DataFrame with 'date' (UTC) and 'value')]; restarts:
    [(times, colour)] drawn as dashed vertical lines."""
    lines = [(name, frame) for name, frame in lines if not frame.empty]
    datasets, series = [], []
    for index, (name, frame) in enumerate(lines):
        datasets.append({"source": frame})
        series.append({
            "type": "line",
            "name": str(name),
            "datasetIndex": index,
            "encode": {"x": "date", "y": "value"},
            "color": PALETTE[index % len(PALETTE)],
            "showSymbol": False,
            "sampling": "lttb",
            "connectNulls": False,
            "lineStyle": {"width": 1 if len(lines) > 12 else 1.5},
            "emphasis": {"focus": "series"},
        })
    if lines:
        x_min = min(frame["date"].iloc[0] for _, frame in lines)
        x_max = max(frame["date"].iloc[-1] for _, frame in lines)
        for times, color in restarts or []:
            inside = [t for t in times if x_min <= pd.Timestamp(t) <= x_max]
            if inside:
                series.append(_restart_series(inside, color))
    axis_font = {"fontSize": font_size} if font_size else {}
    return {
        "animation": False,
        "useUTC": True,
        "title": {"text": title or "", "left": "center", "textStyle": {"fontSize": 14}},
        "legend": {"type": "scroll", "top": 28, "data": [str(name) for name, _ in lines]},
        "grid": {"left": 8, "right": 24, "top": 72, "bottom": 64, "containLabel": True},
        "tooltip": {"trigger": "axis", "confine": True, "axisPointer": {"type": "cross"}},
        "toolbox": {
            "right": 8,
            "top": 0,
            "feature": {
                "dataZoom": {"yAxisIndex": "none", "title": {"zoom": "Zoom", "back": "Undo zoom"}},
                "restore": {"title": "Reset"},
                "saveAsImage": {"title": "Save PNG"},
            },
        },
        "xAxis": {"type": "time", "axisLabel": {"formatter": x_format, "hideOverlap": True, **axis_font}},
        "yAxis": {"type": "value", "scale": True, "name": y_name or "", "axisLabel": axis_font},
        "dataZoom": [
            {"type": "inside", "xAxisIndex": 0, "filterMode": "filter"},
            {"type": "slider", "xAxisIndex": 0, "height": 20, "bottom": 8, "filterMode": "filter"},
        ],
        "dataset": datasets,
        "series": series,
    }


def show(option: dict, height: int, width=None, key: str | None = None) -> None:
    st.echarts_chart(option, height=int(height) + 100, width=int(width) if width else "stretch", key=key)


# --- the chart types of the app -------------------------------------------

def single(df, prop, restart_headers, os_details, title=None, font_size=None) -> dict:
    """Detailed Metrics, one metric (df: index or column 'date', column prop)."""
    dates = df["date"] if "date" in df.columns else df.index
    return build_option(
        [_line(prop, dates, df[prop])],
        [(parse_restart_times(restart_headers, os_details), RESTART_COLOR)],
        title=title, y_name=prop, font_size=font_size,
    )


def metrics(df_long, restart_headers, os_details, title=None, font_size=None) -> dict:
    """Several metrics of one file (long format: date, metrics, y)."""
    lines = [_line(name, part["date"], part["y"]) for name, part in df_long.groupby("metrics", sort=False)]
    return build_option(
        lines,
        [(parse_restart_times(restart_headers, os_details), RESTART_COLOR)],
        title=title, font_size=font_size,
    )


def devices(df, prop, restart_headers, os_details, title=None, font_size=None) -> dict:
    """Metrics on many devices: one line per sub_device."""
    if isinstance(restart_headers, list) and restart_headers and isinstance(restart_headers[0], list):
        restart_headers = restart_headers[0]
    frame = df.to_pandas() if hasattr(df, "to_pandas") else df
    order = sorted(frame["sub_device"].unique(), key=lambda d: (d != "all", int(d) if str(d).isdigit() else 0, str(d)))
    lines = [_line(device, frame.loc[frame["sub_device"] == device, "date"],
                   frame.loc[frame["sub_device"] == device, prop]) for device in order]
    return build_option(
        lines,
        [(parse_restart_times(restart_headers, os_details), RESTART_COLOR)],
        title=title, y_name=prop, font_size=font_size,
    )


def _file_restarts(file_name: str, reboot_headers) -> list:
    """Restart times of one file; reboot_headers holds [restart headers,
    os_details] per file and is matched by host name and sar date."""
    for header in reboot_headers or []:
        if not header or not header[0]:
            continue
        parts = header[1].split()
        if len(parts) > 3 and parts[2].strip("()") in file_name and parts[3] in file_name:
            return list(parse_restart_times(header[0], header[1]))
    return []


def files_consecutive(chart_field, reboot_headers, title=None, font_size=None) -> dict:
    """Multiple Sar Files one after the other on the real time axis; each
    file's restarts in the colour of its line."""
    prop = chart_field[0][1]
    lines, restarts = [], []
    for index, (df_part, _) in enumerate(chart_field):
        name = df_part["file"].iloc[0] if "file" in df_part and len(df_part) else f"file {index + 1}"
        lines.append(_line(name, df_part["date"], df_part[prop]))
        restarts.append((_file_restarts(str(name), reboot_headers), PALETTE[index % len(PALETTE)]))
    return build_option(lines, restarts, title=title, y_name=prop, font_size=font_size, x_format="{MM}-{dd} {HH}:{mm}")


def files_overlay(chart_field, reboot_headers, title=None, font_size=None) -> dict:
    """Multiple Sar Files laid over one day: every file is moved to the day
    of the earliest one, the axis shows the time of day only."""
    prop = chart_field[0][1]
    parts = [(df_part, df_part["file"].iloc[0] if "file" in df_part and len(df_part) else "") for df_part, _ in chart_field]
    starts = [_utc(df_part["date"]).dt.normalize().min() for df_part, _ in parts if len(df_part)]
    if not starts:
        return build_option([])
    base = min(starts)
    lines, restarts = [], []
    for index, (df_part, name) in enumerate(parts):
        dates = _utc(df_part["date"])
        aligned = base + (dates - dates.dt.normalize())
        lines.append(_line(name, aligned, df_part[prop]))
        times = [pd.Timestamp(t) for t in _file_restarts(str(name), reboot_headers)]
        aligned_restarts = [base + (t - t.normalize()) for t in times]
        restarts.append((aligned_restarts, PALETTE[index % len(PALETTE)]))
    return build_option(lines, restarts, title=title, y_name=prop, font_size=font_size)


def compare(chart_field, restart_headers, os_details, title=None, font_size=None) -> dict:
    """Compare Metrics: chart_field holds [df indexed by date, metric] per box."""
    lines = [_line(metric, df_part.index, df_part[metric]) for df_part, metric in chart_field
             if df_part is not None and not df_part.empty]
    return build_option(
        lines,
        [(parse_restart_times(restart_headers, os_details), RESTART_COLOR)],
        title=title, font_size=font_size,
    )
