"""Chart orchestration: build figures the same way the UI pages do and
render them to PNG/PDF bytes."""

import io
import zipfile
from pathlib import Path

from . import bootstrap  # noqa: F401
from . import rendering, services
from .services import ServiceError

import pl_helpers2 as pl_h2
import helpers_pl as helpers


def _validate(backend: str, fmt: str) -> None:
    if backend not in ("bokeh", "altair"):
        raise ServiceError(f"Unknown backend {backend!r} (bokeh|altair)")
    if fmt not in ("png", "pdf"):
        raise ServiceError(f"Unknown format {fmt!r} (png|pdf)")


def _render(chart_obj, backend: str, fmt: str) -> bytes:
    if backend == "altair":
        return rendering.altair_bytes(chart_obj, fmt)
    if fmt == "png":
        return rendering.bokeh_png_bytes(chart_obj)
    return rendering.bokeh_pdf_bytes(chart_obj)


def _build_single_figure(
    table,
    meta: dict,
    metric: str | None,
    backend: str,
    width: int,
    height: int,
    font_size: int,
    title: str,
):
    """Mirrors single_file_pl.single_f: one metric -> draw_single_chart_v1,
    all metrics of the header -> overview_v1."""
    import alt as alt_charts
    import bokeh_charts

    restart_headers = meta["restart_headers"]
    os_details = meta["os_details"]

    if metric:
        df_part = table[[metric]].copy()
        df_part["file"] = os_details.split()[2].strip("()")
        df_part["date"] = df_part.index
        df_part["metric"] = metric
        if backend == "bokeh":
            _, fig = bokeh_charts.draw_single_chart_v1(
                df_part, metric, restart_headers, os_details,
                width, height, font_size=font_size, title=title, embed_html=False,
            )
            return fig
        return alt_charts.draw_single_chart_v1(
            df_part, metric, restart_headers, os_details,
            width, height, font_size=font_size, title=title,
        )

    if backend == "bokeh":
        _, fig = bokeh_charts.overview_v1(
            table, restart_headers, os_details,
            font_size=font_size, width=width, height=height, title=title,
            embed_html=False,
        )
        return fig
    melted = table.reset_index().melt("date", var_name="metrics", value_name="y")
    return alt_charts.overview_v1(
        melted, restart_headers, os_details,
        font_size=font_size, width=width, height=height, title=title,
    )


def single_chart(
    username: str,
    name: str,
    header_name: str,
    metric: str | None = None,
    device: str | None = None,
    start: str | None = None,
    end: str | None = None,
    backend: str = "bokeh",
    fmt: str = "png",
    width: int = 1200,
    height: int = 400,
    font_size: int = 12,
    title: str | None = None,
) -> tuple[bytes, str]:
    """Returns (payload, filename)."""
    _validate(backend, fmt)
    table, meta = services.get_table(
        username, name, header_name, metric=None, device=device, start=start, end=end
    )
    if metric and metric not in table.columns:
        raise ServiceError(
            f"Unknown metric {metric!r}; available: {list(table.columns)}"
        )
    chart_title = title or " ".join(
        x for x in (meta["alias"], meta["device"], metric) if x
    )
    fig = _build_single_figure(
        table, meta, metric, backend, width, height, font_size, chart_title
    )
    payload = _render(fig, backend, fmt)
    filename = f"{name}_{helpers.validate_convert_names(chart_title)}.{fmt}"
    return payload, filename


def overview(
    username: str,
    name: str,
    aliases: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    backend: str = "bokeh",
    fmt: str = "pdf",
    width: int = 1200,
    height: int = 400,
    font_size: int = 12,
) -> tuple[bytes, str, str]:
    """Graphical overview over several headers.

    fmt='pdf' -> one multi-page PDF (like the UI's whole-page download),
    fmt='png' -> zip archive with one PNG per header/device.
    Returns (payload, filename, media_type).
    """
    _validate(backend, fmt)
    df = services.load_df(username, name)
    aliases = aliases or services.DEFAULT_OVERVIEW_ALIASES

    figures: list[tuple[str, object]] = []
    for alias in aliases:
        header, resolved_alias = services.resolve_header(df, alias)
        for frame in services.prepare_header_frames(df, header):
            table = services.filter_time_range(frame["df"], start, end)
            meta = {
                "restart_headers": pl_h2.get_restart_headers(df),
                "os_details": pl_h2.get_os_details_from_df(df).strip(),
            }
            chart_title = " ".join(
                x for x in (resolved_alias, str(frame["sub_title"] or "")) if x
            )
            fig = _build_single_figure(
                table, meta, None, backend, width, height, font_size, chart_title
            )
            figures.append((chart_title, fig))

    if fmt == "pdf":
        pages = []
        for _, fig in figures:
            if backend == "bokeh":
                pages.append(rendering.bokeh_pdf_bytes(fig))
            else:
                pages.append(rendering.altair_bytes(fig, "pdf"))
        return rendering.merge_pdfs(pages), f"{name}_overview.pdf", "application/pdf"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for chart_title, fig in figures:
            png = (
                rendering.bokeh_png_bytes(fig)
                if backend == "bokeh"
                else rendering.altair_bytes(fig, "png")
            )
            archive.writestr(
                f"{helpers.validate_convert_names(chart_title)}.png", png
            )
    return buffer.getvalue(), f"{name}_overview_png.zip", "application/zip"


def multi_file_chart(
    username: str,
    names: list[str],
    header_name: str,
    metric: str,
    device: str | None = None,
    mode: str = "overlay",
    backend: str = "bokeh",
    fmt: str = "png",
    width: int = 1200,
    height: int = 400,
    font_size: int = 12,
) -> tuple[bytes, str]:
    """Compare one metric across files (multi_files_pl.single_multi).

    mode='overlay'   -> all days on one faked 24h axis (overview_v6)
    mode='sequential'-> files side by side on the real time axis (overview_v3)
    """
    import alt as alt_charts
    import bokeh_charts

    _validate(backend, fmt)
    if mode not in ("overlay", "sequential"):
        raise ServiceError(f"Unknown mode {mode!r} (overlay|sequential)")
    if len(names) < 2:
        raise ServiceError("At least two files are required for a comparison")

    chart_field = []
    reboot_headers = []
    main_alias = None
    for name in names:
        df = services.load_df(username, name)
        header, alias = services.resolve_header(df, header_name)
        main_alias = main_alias or alias
        reboot_headers.append(
            [pl_h2.get_restart_headers(df), pl_h2.get_os_details_from_df(df)]
        )
        frames = services.prepare_header_frames(df, header, device)
        table = frames[0]["df"]
        if metric not in table.columns:
            raise ServiceError(
                f"{name}: unknown metric {metric!r}; available: {list(table.columns)}"
            )
        df_part = table[[metric]].copy()
        df_part["file"] = Path(name).name
        df_part["date"] = df_part.index
        chart_field.append([df_part, metric])

    title = f"{main_alias} {device}" if device else main_alias
    if backend == "bokeh":
        if mode == "sequential":
            _, fig = bokeh_charts.overview_v3(
                chart_field, reboot_headers, width, height, "file", font_size,
                title=title, embed_html=False,
            )
        else:
            _, fig = bokeh_charts.overview_v6(
                chart_field, reboot_headers, width, height, font_size,
                title=title, embed_html=False,
            )
    else:
        if mode == "sequential":
            fig = alt_charts.overview_v3(
                chart_field, reboot_headers, width, height, "file", font_size,
                title=title,
            )
        else:
            fig = alt_charts.overview_v6(
                chart_field, reboot_headers, width, height, font_size, title=title
            )
        fig = fig.configure_axisY(labelLimit=400)

    payload = _render(fig, backend, fmt)
    filename = (
        f"multi_{helpers.validate_convert_names(title)}_"
        f"{helpers.validate_convert_names(metric)}.{fmt}"
    )
    return payload, filename
