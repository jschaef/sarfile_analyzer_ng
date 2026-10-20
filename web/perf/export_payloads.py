#!/usr/bin/env python3
"""Export the chart payloads for perf/bench.mjs (ECharts vs BokehJS).

Run from the repo root with the venv of code/ + api/ (read-only use of both):

    UPLOAD_DIR=... python3 web/perf/export_payloads.py --user admin \
        --file 2026-10-20_bighost_2026-10-01 --out web/perf/out

Writes per scenario:
  <scenario>.bokeh.json    json_item() of bokeh_charts.overview_v1 - exactly what
                           streamlit_bokeh_component.serialize_figure produces
  <scenario>.echarts.json  rows as GET /files/{name}/data returns them (the
                           Next.js frontend's input)
  <scenario>.echarts-same.json  the rows the Bokeh figure actually contains after
                           its server-side down-sampling (same points for both)
  meta.json                sizes, row/series counts, server-side timings, versions

Scenarios:
  cpu-overview  CPU 'all' aggregate, 10 metrics - the CPU chart of the
                Graphical Overview (dia_overview_pl / services.get_table)
  cpu-per-core  %usr of every single CPU as its own series (stress case beyond
                the overview: ~1M points for 352 CPUs x 2833 samples)
"""

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from api import bootstrap  # noqa: E402,F401  (puts code/ on sys.path)
from api import services  # noqa: E402

import bokeh  # noqa: E402
import bokeh_charts  # noqa: E402
import pandas as pd  # noqa: E402
import pl_helpers2 as pl_h2  # noqa: E402
import polars as pl  # noqa: E402
from bokeh.embed import json_item  # noqa: E402

WIDTH, HEIGHT = 1200, 400


def api_rows(table: pd.DataFrame) -> list[dict]:
    """Same transformation as api/main.py get_data()."""
    records = table.reset_index()
    records["date"] = records["date"].astype(str)
    return records.to_dict(orient="records")


def bokeh_payload(table: pd.DataFrame, title: str, os_details: str) -> tuple[str, float, float]:
    t0 = time.perf_counter()
    _, fig = bokeh_charts.overview_v1(
        table, [], os_details, font_size=12, width=WIDTH, height=HEIGHT,
        title=title, embed_html=False,
    )
    t1 = time.perf_counter()
    payload = json.dumps(json_item(fig))
    t2 = time.perf_counter()
    return payload, (t1 - t0) * 1000, (t2 - t1) * 1000


def sampled_like_bokeh(table: pd.DataFrame) -> pd.DataFrame:
    """The rows overview_v1 keeps (its own stride sampling)."""
    series = len(table.columns)
    return bokeh_charts.sample_dataframe_for_viz(
        table, max_rows=bokeh_charts._adaptive_max_rows_for_series(series)
    )


def per_core_table(username: str, name: str) -> pd.DataFrame:
    df = services.load_df(username, name)
    header, alias = services.resolve_header(df, "CPU")
    df_h = pl_h2.get_data_frames_from__headers([header], df, "header")[0]
    metrics = pl_h2.get_metrics_from_df(df_h, header, alias)
    usr_index = header.split().index("%usr")
    wide = (
        metrics.filter(pl.col("sub_device") != "all")
        .with_columns(pl.col(header).list.get(usr_index).alias("value"))
        .select("date", "sub_device", "value")
        .pivot(on="sub_device", index="date", values="value")
        .sort("date")
    )
    cores = sorted((c for c in wide.columns if c != "date"), key=int)
    return wide.select("date", *cores).to_pandas().set_index("date")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="admin")
    parser.add_argument("--file", required=True)
    parser.add_argument("--out", default=str(Path(__file__).parent / "out"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cpu_table, meta = services.get_table(args.user, args.file, "CPU")
    tables = {
        "cpu-overview": (cpu_table, "CPU all"),
        "cpu-per-core": (per_core_table(args.user, args.file), "CPU %usr per core"),
    }

    info: dict = {
        "file": args.file,
        "versions": {"bokeh": bokeh.__version__, "pandas": pd.__version__, "polars": pl.__version__},
        "chart_size": [WIDTH, HEIGHT],
        "scenarios": {},
    }
    for scenario, (table, title) in tables.items():
        bokeh_json, build_ms, serialize_ms = bokeh_payload(table, title, meta["os_details"])
        same = sampled_like_bokeh(table)
        files = {
            "bokeh": bokeh_json,
            "echarts": json.dumps({"rows": len(table), "data": api_rows(table)}),
            "echarts-same": json.dumps({"rows": len(same), "data": api_rows(same)}),
        }
        for kind, text in files.items():
            (out / f"{scenario}.{kind}.json").write_text(text)
        info["scenarios"][scenario] = {
            "series": len(table.columns),
            "rows_full": len(table),
            "rows_bokeh_sampled": len(same),
            "points_full": len(table) * len(table.columns),
            "points_bokeh": len(same) * len(table.columns),
            "bytes": {kind: len(text.encode()) for kind, text in files.items()},
            "python_ms": {"bokeh_build_figure": round(build_ms, 1), "bokeh_json_item": round(serialize_ms, 1)},
        }
        print(scenario, json.dumps(info["scenarios"][scenario]))
    (out / "meta.json").write_text(json.dumps(info, indent=2))

    static = Path(bokeh.__file__).parent / "server" / "static" / "js" / "bokeh.min.js"
    (out / "bokeh.min.js").write_bytes(static.read_bytes())


if __name__ == "__main__":
    main()
