import streamlit as st
import os
import helpers_pl as helpers
import pandas as pd

global fobject


def create_pdf(file: str, chart: object) -> list:
    global fobject
    mimetype = "application/x-binary"
    chart.save(file)
    fobject = open(file, "rb")
    return [fobject, mimetype]

def pdf_download(file: str, chart: object, key=None, download_name=None):
    """creates a download button and a checkbox. Using function create_pdf()
    to create the file for download if the checkbox has been enabled.

    Args:
        file (str): filepath where to save the pdf
        chart (altair object): image/chart created from the altair library
        key (widget key, optional): widget key for streamlit api. Defaults to None.
    """
    col1, col2, *_ = st.columns([0.1, 0.1, 0.8])
    col2 = col2 if col2 else st
    save_dir = os.path.dirname(file)
    if not os.path.exists(save_dir):
        os.system(f"mkdir -p {save_dir}")

    if not download_name:
        download_name = "sar_chart.pdf"

    if col1.button("prepare PDF", key=key):
        col1.download_button(
            key = f"{key}_download",
            label="Download PDF",
            file_name=download_name,
            data=create_pdf(file, chart)[0],
            mime="application/x-binary",
            on_click="ignore",
            type="primary",
        )
    try:
        fobject
    except NameError:
        pass
    else:
        fobject.close()


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


def create_columns(number: int, write_field: list = None) -> list:
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
    st.markdown("___")
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
                pcols[index].markdown("___")
                pcols[index].markdown(f"###### {header}")
                for nindex in range(1, rcols + 1):
                    nindex = cols_per_line - nindex
                    pcols[nindex].write("")
            pcols[index].write(object)
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

def make_vspace(size: int, col: object) -> None:
    col.write(f"{size * '#'}")

def make_big_vspace(size:int, col: object) -> None:
    for x in range(size):
        make_vspace(1, col)
