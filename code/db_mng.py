#!/usr/bin/python3
import streamlit as st
import sql_stuff
import sqlite2_polars
import polars as pl
import pandas as pd
import layout_helper_pl as lh
import visual_funcs as visf


def db_mgmt(headings_df: pl.DataFrame, metrics_df: pl.DataFrame):
    col, _, _, _ = visf.create_columns(4, [0, 1, 1, 1])
    widget = col.selectbox("Data", ["metrics", "headers"])
    if widget == "metrics":
        action = col.selectbox("Actions", ["Show", "Add", "Search", "Delete"])
        if action == "Add":
            col.subheader("Apply metric")
            col.write("This metric will be applied to the database")
            metric_placeholder = col.empty()
            m_content = metric_placeholder.text_input("metric", key="m_key")
            col, _ = visf.create_columns(2, [0, 1])
            mdesc_placeholder = col.empty()
            d_content = mdesc_placeholder.text_area("metric description", key="d_key")
            if col.button("Submit") and (m_content or d_content):
                sql_stuff.add_metric(m_content, d_content)
                m_content = metric_placeholder.text_input("metric name")
                d_content = mdesc_placeholder.text_area("metric description")
        elif action == "Show":
            col, _ = st.columns([0.7, 0.3])
            df = (
                pd.DataFrame(
                    sqlite2_polars.view_all_metrics(), columns=["metric", "description"]
                ),
            )
            col.table(df[0])
        elif action == "Delete":
            metrics = sqlite2_polars.view_all_metrics()
            metrics = [x[0] for x in metrics]
            multid_placeholder = col.empty()
            del_list = multid_placeholder.multiselect(
                "Choose metrics to delete", metrics, key="d_multi"
            )
            if st.button("Submit"):
                for metric in del_list:
                    sql_stuff.delete_metric(metric)
                    metrics.remove(metric)
                del_list = multid_placeholder.multiselect(
                    "Choose metrics to delete", metrics
                )
        elif action == "Search":
            metrics = sqlite2_polars.view_all_metrics()
            metrics = [x[0] for x in metrics]
            search_list = col.multiselect(
                "Choose metrics to display", metrics, key="s_metric", 
            )

            if search_list:
                col, _ = visf.create_columns(2, [0.7, 0.3])
                col.table(
                    pd.DataFrame(
                        sqlite2_polars.view_all_metrics(), columns=["metric", "description"]
                    ).loc[lambda df: df["metric"].isin(search_list)]
                )
    elif widget == "headers":
        action = col.selectbox("Actions", ["Show", "Add", "Delete", "Update", "Search"])
        col, _, _, _ = visf.create_columns(4, [0, 0, 0, 1])
        if action == "Add":
            h_placeholder = col.empty()
            h_content = h_placeholder.text_input("Header", key="head_key")
            a_placeholder = col.empty()
            a_content = a_placeholder.text_input("Alias", key="alias_key")
            k_placeholder = col.empty()
            k_content = k_placeholder.text_input("Keyword", key="keywd")
            d_placeholder = col.empty()
            d_content = d_placeholder.text_area("Description", key="description")
            if st.button("Submit"):
                sql_stuff.add_header(h_content, d_content, a_content, k_content)
                h_content = h_placeholder.text_input("Header")
                a_content = a_placeholder.text_input("Alias")
                k_content = k_placeholder.text_input("Keyword")
                d_content = d_placeholder.text_area("Description")
        elif action == "Delete":
            h_ph = col.empty()
            h_content = h_ph.selectbox(
                "Choose a header to delete",
                sqlite2_polars.ret_all_headers(headings_df, "return"),
                key="hd_key",
            )
            if st.button("Submit"):
                sql_stuff.delete_header(h_content)
                h_content = h_ph.selectbox(
                    "Choose a header to delete",
                    sqlite2_polars.ret_all_headers(headings_df, "return"),
                )

        elif action == "Show":
            col, _ = st.columns([0.7, 0.3])
            col.table(pd.DataFrame(sqlite2_polars.ret_all_headers(headings_df, "show"),
               columns=["header", "alias", "description","keyword"] ))

        elif action == "Update":
            a_sel_ph = col.empty()
            a_sel = a_sel_ph.selectbox(
                "Choose an alias to update",
                sqlite2_polars.ret_all_aliases(headings_df),
                key="al_key",
            )
            header = sqlite2_polars.get_header_from_alias(a_sel)
            u_ph = col.empty()
            u_content = u_ph.text_area("Update Header", value=header, key="uh_key")
            a_placeholder = col.empty()
            a_content = a_placeholder.text_input("Alias", key="ualias_key", value=a_sel)
            k_placeholder = col.empty()
            k_content = k_placeholder.text_input(
                "Keyword",
                key="ukwd_key",
                value=sqlite2_polars.get_header_prop(header, "keywd"),
            )
            d_placeholder = col.empty()
            d_content = d_placeholder.text_input(
                "Description",
                key="ud_key",
                value=sqlite2_polars.get_header_prop(header, "description"),
            )

            if st.button("Submit"):
                sql_stuff.update_header(
                    header,
                    header=u_content,
                    alias=a_content,
                    description=d_content,
                    keyword=k_content,
                )

        elif action == "Search":
            m_search_ph = col.empty()
            metric_field = sqlite2_polars.view_all_metrics()
            metric_sel_field = list(
                set([x[0] for x in metric_field if x[0] == x[0].lower()])
            )
            metric_sel_field.sort()
            m_sel = m_search_ph.selectbox(
                "Choose a metric to search the header for",
                metric_sel_field,
                key="m_key",
            )

            metric_headers = [
                x
                for x in sqlite2_polars.ret_all_headers(headings_df, "return")
                if m_sel in x.split()
            ]
            headings_df = sqlite2_polars.get_table_df("headingstable")
            alias_header_fields = [
                sqlite2_polars.get_exact_value_from_filter(
                    headings_df, "header", x, "alias"
                )
                for x in metric_headers
            ]

            if alias_header_fields:
                lh.make_big_vspace(2, col)
                col.markdown(f"###### Headers for selected {m_sel}")
                st.dataframe(
                    pl.DataFrame(
                        [alias_header_fields, metric_headers], schema=["alias", "header"]
                    )
                )
            
            else:
                col.warning(f"A header for {m_sel} does yet not exist")
