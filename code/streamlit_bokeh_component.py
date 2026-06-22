"""Thin wrapper to render Bokeh figures via the `streamlit-bokeh` custom component.

We intentionally register the component using Streamlit Components v1 `declare_component`
pointing at the package's bundled frontend build.

Why: `streamlit-bokeh` currently uses Components v2 for Streamlit >= 1.51, which
requires a `pyproject.toml` declaration with `asset_dir`. This repo is not a
packaged component project, so importing `streamlit_bokeh` can raise.

This wrapper works around that by directly using the v1 component registration.
"""

from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path

import streamlit as st
from bokeh.embed import json_item


@lru_cache(maxsize=1)
def _get_component_callable():
    spec = importlib.util.find_spec("streamlit_bokeh")
    if spec is None or not spec.submodule_search_locations:
        raise ModuleNotFoundError(
            "streamlit_bokeh package not found. Install with `pip install streamlit-bokeh`."
        )

    pkg_path = Path(list(spec.submodule_search_locations)[0])
    build_dir = pkg_path / "frontend" / "build"
    if not build_dir.exists():
        raise FileNotFoundError(f"streamlit-bokeh build dir not found: {build_dir}")

    return st.components.v1.declare_component("streamlit_bokeh", path=str(build_dir))


def serialize_figure(figure) -> str:
    """Serialize a Bokeh figure to the JSON string the frontend expects.

    Kept separate so callers can precompute (and cache) the JSON once instead of
    paying the GIL-bound serialization on every rerun.
    """
    return json.dumps(json_item(figure))


def streamlit_bokeh(
    figure,
    *,
    use_container_width: bool = True,
    theme: str = "streamlit",
    key: str | None = None,
    figure_json: str | None = None,
) -> bool:
    """Render a Bokeh figure via the streamlit-bokeh custom component.

    If ``figure_json`` is given it is used as-is and ``figure`` is not
    serialized again — let callers cache the (expensive) JSON across reruns.

    Returns True if the component rendered, False if it failed.
    """

    try:
        component = _get_component_callable()
        component(
            figure=figure_json if figure_json is not None else serialize_figure(figure),
            use_container_width=use_container_width,
            bokeh_theme=theme,
            key=key,
        )
        return True
    except Exception:
        return False
