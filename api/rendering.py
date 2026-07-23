"""Chart rendering to PNG/PDF bytes, headless.

Bokeh needs a Selenium Firefox driver (same mechanism as the UI, but with a
plain module-level pool singleton instead of @st.cache_resource). Altair
renders via vl-convert with no browser dependency.
"""

import io
import os
import tempfile
import threading

from . import bootstrap  # noqa: F401

from pypdf import PdfWriter

_pool = None
_pool_lock = threading.Lock()


class _ApiDriverPool:
    """Lazily built driver pool: Firefox first (like the UI), Chrome as
    fallback for hosts without Firefox (Selenium Manager fetches the
    chromedriver automatically)."""

    def __new__(cls):
        from driver_pool import BokehDriverPool

        class Pool(BokehDriverPool):
            def _create_driver(self):
                try:
                    return super()._create_driver()
                except Exception:
                    from selenium import webdriver
                    from selenium.webdriver.chrome.options import Options

                    options = Options()
                    options.add_argument("--headless=new")
                    options.add_argument("--disable-gpu")
                    options.add_argument("--no-sandbox")
                    options.add_argument("--disable-dev-shm-usage")
                    options.add_argument("--force-device-scale-factor=1")
                    return webdriver.Chrome(options=options)

        cpu_count = os.cpu_count() or 4
        return Pool(max_drivers=max(1, min(int(cpu_count * 0.5), 4)))


def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = _ApiDriverPool()
        return _pool


def bokeh_png_bytes(fig) -> bytes:
    from bokeh.io import export_png

    pool = _get_pool()
    driver = pool.acquire()
    if driver is None:
        raise RuntimeError(
            "No Selenium Firefox driver available for Bokeh export "
            "(is Firefox installed?). Use backend=altair as an alternative."
        )
    png_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            png_path = tmp.name
        export_png(fig, filename=png_path, webdriver=driver)
        with open(png_path, "rb") as fh:
            return fh.read()
    finally:
        pool.release(driver)
        if png_path and os.path.exists(png_path):
            os.unlink(png_path)


def png_to_pdf_bytes(png_data: bytes) -> bytes:
    from PIL import Image

    with Image.open(io.BytesIO(png_data)) as image:
        if image.mode == "RGBA":
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PDF", resolution=100.0)
        return buffer.getvalue()


def bokeh_pdf_bytes(fig) -> bytes:
    return png_to_pdf_bytes(bokeh_png_bytes(fig))


def altair_bytes(chart, fmt: str) -> bytes:
    buffer = io.BytesIO()
    chart.save(buffer, format=fmt)  # 'png' or 'pdf' via vl-convert
    return buffer.getvalue()


def merge_pdfs(pdf_pages: list[bytes]) -> bytes:
    merger = PdfWriter()
    try:
        for page in pdf_pages:
            merger.append(io.BytesIO(page))
        out = io.BytesIO()
        merger.write(out)
        return out.getvalue()
    finally:
        merger.close()
