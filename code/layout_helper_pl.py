import streamlit as st
from streamlit.delta_generator import DeltaGenerator
import os
import helpers_pl as helpers
import pandas as pd
import tempfile
from typing import Any


def _stable_pdf_key(prefix: str, name: str | None) -> str:
    """Create a stable Streamlit widget key from a human-readable name."""
    base = (name or "sar_chart").strip()
    return f"{prefix}_{helpers.validate_convert_names(base)}"


def create_pdf(file: str, chart: Any) -> list:
    #global fobject
    mimetype = "application/x-binary"
    chart.save(file)
    fobject = open(file, "rb")
    return [fobject, mimetype]

@st.fragment
def pdf_download(file: str, chart: Any, key=None, download_name=None):
    """creates a download button that generates PDF only when prepare button is clicked.

    Args:
        file (str): filename (not used for saving, only for naming)
        chart (altair object): image/chart created from the altair library
        key (widget key, optional): widget key for streamlit api. Defaults to None.
        download_name (str, optional): name for the downloaded file
    """
    if not download_name:
        download_name = "sar_chart.pdf"
    if key is None:
        key = _stable_pdf_key("pdf_prepare", download_name)

    col1, col2, *_ = st.columns([0.1, 0.1, 0.8])
    
    # Only generate PDF when user clicks the prepare button
    if col1.button("prepare PDF", key=key):
        # Create temporary file for the PDF
        temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
        os.close(temp_fd)
        
        try:
            # Generate PDF data
            chart.save(temp_path)
            with open(temp_path, "rb") as f:
                pdf_data = f.read()
            
            # Show download button
            col1.download_button(
                key=f"{key}_download",
                label="Download PDF",
                file_name=download_name,
                data=pdf_data,
                mime="application/pdf",
                type="primary",
            )
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)

def pdf_download_direct(chart: Any, download_name: str, key: str = None):
    """Direct PDF download button without prepare step.
    
    Generates PDF data immediately and provides download button.
    Use this for single-chart pages where immediate download is preferred.
    
    Args:
        chart: Altair chart object to convert to PDF
        download_name: Filename for the downloaded PDF
        key: Optional unique key for the download button
    """
    if key is None:
        key = _stable_pdf_key("pdf_download", download_name)

    import io
    
    # Generate PDF data in memory
    pdf_buffer = io.BytesIO()
    chart.save(pdf_buffer, format='pdf')
    pdf_buffer.seek(0)
    
    # Create download button
    _ = st.download_button(
        label="Download PDF",
        data=pdf_buffer.getvalue(),
        file_name=download_name,
        mime="application/pdf",
        key=key if key else f"pdf_{download_name}"
    )

@st.fragment
def pdf_download_bokeh(plot_obj: Any, download_name: str, key: str | None = None):
    """Two-step Bokeh PDF export: Prepare → Download.

    Requirements this satisfies:
    - One Prepare button per diagram.
    - Clicking Prepare should not refresh the whole page (fragment rerun only).
    - After preparing, show a Download button in the same place.
    - Clicking Download may refresh; when wrapped in a fragment it usually won't.

    Notes:
    - `dia_overview_pl.cleanup_chart_memory()` deletes keys containing `'_pdf'`.
      This helper stores bytes under keys that avoid that substring so prepared
      data isn't accidentally cleared on unrelated reruns.
    """

    if key is None:
        key = _stable_pdf_key("bokehpdf_prepare", download_name)

    prepared_bytes_key = f"{key}__bytes"

    import io
    import os
    import tempfile
    import time
    from bokeh.io import export_png
    from PIL import Image
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options

    def _prepare_clicked() -> bool:
        try:
            from streamlit.errors import StreamlitAPIException
        except Exception:  # pragma: no cover
            StreamlitAPIException = Exception

        try:
            return st.button("Prepare PDF", key=key, help="Generate the PDF and show the download button")
        except StreamlitAPIException:
            # Fallback if this is ever used inside a form
            return st.form_submit_button("Prepare PDF", key=key)

    if _prepare_clicked():
        png_path = None
        driver = None
        try:
            try:
                import geckodriver_autoinstaller

                geckodriver_autoinstaller.install()
            except Exception:
                pass

            firefox_options = Options()
            firefox_options.add_argument('--headless')
            firefox_options.add_argument('--disable-gpu')
            firefox_options.add_argument('--no-sandbox')

            driver = webdriver.Firefox(options=firefox_options)

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_png:
                png_path = tmp_png.name

            export_png(plot_obj, filename=png_path, webdriver=driver)
            time.sleep(0.2)

            image = Image.open(png_path)
            if image.mode == 'RGBA':
                image = image.convert('RGB')

            pdf_buffer = io.BytesIO()
            image.save(pdf_buffer, format='PDF', resolution=100.0)
            st.session_state[prepared_bytes_key] = pdf_buffer.getvalue()
        except Exception as e:
            st.error(f"PDF export failed: {e}")
            st.session_state.pop(prepared_bytes_key, None)
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
            if png_path and os.path.exists(png_path):
                try:
                    os.unlink(png_path)
                except Exception:
                    pass

    pdf_bytes = st.session_state.get(prepared_bytes_key)
    if pdf_bytes:
        st.download_button(
            label="Download PDF",
            data=pdf_bytes,
            file_name=download_name,
            mime="application/pdf",
            key=f"{key}__download",
            type="primary",
        )


def pdf_download_bokeh_direct(plot_obj: Any, download_name: str, key: str = None):
    """Single-click PDF download for Bokeh plots (deferred generation).

    Uses Streamlit's newer `download_button(..., data=callable)` support so the PDF is
    generated *only when the user clicks* "Download PDF". Nothing is cached in
    `st.session_state` and no files are persisted.

    Note: The callable runs in a separate thread; Streamlit calls inside it are ignored.
    """

    if key is None:
        key = _stable_pdf_key("pdf_download", download_name)

    def _generate_pdf_bytes() -> bytes:
        import io
        import os
        import tempfile
        import time
        from bokeh.io import export_png
        from PIL import Image
        from selenium import webdriver
        from selenium.webdriver.firefox.options import Options

        # Auto-install geckodriver if needed
        try:
            import geckodriver_autoinstaller

            geckodriver_autoinstaller.install()
        except Exception:
            pass

        firefox_options = Options()
        firefox_options.add_argument('--headless')
        firefox_options.add_argument('--disable-gpu')
        firefox_options.add_argument('--no-sandbox')

        driver = webdriver.Firefox(options=firefox_options)
        png_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_png:
                png_path = tmp_png.name

            export_png(plot_obj, filename=png_path, webdriver=driver)
            time.sleep(0.2)

            image = Image.open(png_path)
            if image.mode == 'RGBA':
                image = image.convert('RGB')

            pdf_buffer = io.BytesIO()
            image.save(pdf_buffer, format='PDF', resolution=100.0)
            return pdf_buffer.getvalue()
        finally:
            try:
                driver.quit()
            except Exception:
                pass
            if png_path and os.path.exists(png_path):
                try:
                    os.unlink(png_path)
                except Exception:
                    pass

    st.download_button(
        label="Download PDF",
        data=_generate_pdf_bytes,
        file_name=download_name,
        mime="application/pdf",
        key=key,
    )

def show_metrics(prop_list, col=None, key=None, checkbox=None):
    col = col if col else st
    if key:
        if col.checkbox("Show Metric descriptions from man page", key=key):
            for metric in prop_list:
                helpers.metric_expander(metric, col=col)
    elif checkbox != "off":
        if col.checkbox("Show Metric descriptions from man page"):
            for metric in prop_list:
                helpers.metric_expander(metric, col=col)
    else:
        for metric in prop_list:
            helpers.metric_expander(metric, col=col)


def create_columns(number: int, write_field: list | None = None) -> list:
    """Create columns and write empty string into them
       if the column index in write_field is True
    Args:
        number (integer): number of columns
        write_field (list):
    """
    cols = st.columns(number)
    if write_field:
        for entry in range(len(write_field)):
            if write_field[entry]:
                col = cols[entry]
                col.write("")
    return cols


def arrange_grid_entries(object_field, cols_per_line):
    # check if there are selectboxes < cols_per_line left
    total_columns = len(object_field)
    even_lines = int(total_columns / cols_per_line)
    remaining_cols = total_columns % cols_per_line
    rcols = remaining_cols
    empty_cols = cols_per_line - rcols
    if even_lines == 0:
        even_lines = 1
        remaining_cols = 0
    st.markdown("######")
    pcols = st.columns(cols_per_line)

    for _ in range(even_lines):
        collect_field = []
        # more than cols_per_line found
        if total_columns >= cols_per_line:
            for index in range(cols_per_line):
                if object_field:
                    object = object_field.pop(0)
                    collect_field.append(object)
            for index in range(len(collect_field)):
                object = collect_field[index][0]
                stats = collect_field[index][1]
                header = collect_field[index][2]
                if header:
                    pcols[index].markdown(f"###### {header}")
                pcols[index].write(object)
                pcols[index].markdown("###")
                pcols[index].markdown("###### statistics")
                pcols[index].write(stats)

        # less than cols_per_line found
        else:
            for index in range(cols_per_line):
                if object_field:
                    object = object_field.pop(0)
                    collect_field.append(object)
            for index in range(len(collect_field)):
                object = collect_field[index][0]
                stats = collect_field[index][1]
                header = collect_field[index][2]
                if header:
                    pcols[index].markdown(f"###### {header}")
                    for nindex in range(1, empty_cols + 1):
                        nindex = cols_per_line - nindex
                        pcols[nindex].write("")
                pcols[index].write(object)
                pcols[index].markdown("###")
                pcols[index].markdown("###### statistics")
                pcols[index].write(stats)

    # remaining tables
    if remaining_cols:
        collect_field = []
        for index in range(remaining_cols):
            if object_field:
                object = object_field.pop()
                collect_field.append(object)
        for index in range(len(collect_field)):
            object = collect_field[index][0]
            stats = collect_field[index][1]
            header = collect_field[index][2]
            if header:
                pcols[index].markdown("###")
                pcols[index].markdown(f"###### {header}")
            pcols[index].write(object)
            pcols[index].markdown("###")
            pcols[index].markdown("###### statistics")
            pcols[index].write(stats)


def display_averages(dia_field, prop, main_title, sub_item):
    final_dfs = []
    final_dfs_sum = []
    col1, col2 = st.columns([0.3, 0.7])
    if sub_item:
        col1.markdown(f"##### Average statistics for {main_title}/{sub_item}/{prop}")
        col2.markdown(f"##### Average statistics for {main_title}/{sub_item}")
    else:
        col1.markdown(f"##### Average statistics for {main_title}/{prop}")
        col2.markdown(f"##### Average statistics for {main_title}")

    st.write("\n")

    for entry in range(len(dia_field)):
        st.markdown(f"- {dia_field[entry][0]}")

    st.write("\n")

    for entry in range(len(dia_field)):
        df = dia_field[entry][1][prop]
        df_sum = dia_field[entry][1]
        df = df.reset_index()
        df_sum = df_sum.reset_index()
        final_dfs.append(df)
        final_dfs_sum.append(df_sum)
    final_df = pd.concat(final_dfs)
    final_dfs_sum = pd.concat(final_dfs_sum)
    col1, col2 = st.columns([0.3, 0.7])
    final_df.set_index("date", inplace=True)
    final_dfs_sum.set_index("date", inplace=True)
    col1.write(final_df.describe())
    col2.write(final_dfs_sum.describe())

def delete_large_obj():
    for item in st.session_state:
        if "_obj" in item:
            st.session_state.pop(item)
def make_vspace(size: int, col: DeltaGenerator) -> None:
    col.write(f"{size * '#'}")

def make_big_vspace(size:int, col: DeltaGenerator) -> None:
    for x in range(size):
        make_vspace(1, col)

def display_timezone_chooser(col: DeltaGenerator):
    tz_choose = col.toggle("Display data for a Time Zone different from UTC",)
    if tz_choose:
        user_tz = st.context.timezone
        if user_tz and '/' in user_tz:
            user_pre_tz = user_tz.split('/')[0]
        else:
            user_pre_tz = user_tz if user_tz else 'UTC'
        tz_prefixes = helpers.get_time_zone_prefixs()
        tz_index = tz_prefixes.index(user_pre_tz)
        tz_pr_choose = col.selectbox("Choose Region", 
            tz_prefixes, index=tz_index, key="tz_choose")
        # tz_suffixes_index = helpers.get_time_zone_suffixs(tz_pr_choose).index(tz_pr_choose)
        tz_suffixes = helpers.get_time_zone_suffixs(tz_pr_choose)
        if not tz_suffixes:
            tz_suffixes = ['UTC']
        if user_tz and tz_pr_choose in user_tz and user_tz in tz_suffixes:
            tz_suffixes_index = tz_suffixes.index(user_tz)
        else:
            tz_suffixes_index = 0
        return col.selectbox("Choose Time Zone",
            tz_suffixes, index=tz_suffixes_index, key="tz_suffix_choose")
    return None
