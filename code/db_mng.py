#!/usr/bin/python3
import streamlit as st
import sql_stuff
import sqlite2_polars
import polars as pl
import pandas as pd
import visual_funcs as visf

def db_mgmt(headings_df: pl.DataFrame, metrics_df: pl.DataFrame):
    col, _, _, _ = visf.create_columns(4, [0,1,1,1])
    widget = col.selectbox(
        'Data', ['metrics', 'headers'])
    if widget == 'metrics':
        action = col.selectbox(
            'Actions', ['Show', 'Add', 'Delete'])
        if action == 'Add':
            col.subheader('Apply metric')
            col.write(
                'This metric will be applied to the database')
            metric_placeholder = col.empty()    
            m_content = metric_placeholder.text_input('metric', key='m_key')
            col,_ = visf.create_columns(2,[0,1])
            mdesc_placeholder = col.empty()
            d_content = mdesc_placeholder.text_area('metric description', key='d_key')
            if col.button('Submit') and (m_content or  d_content):
                sql_stuff.add_metric(m_content, d_content)
                m_content = metric_placeholder.text_input('metric name')
                d_content = mdesc_placeholder.text_area('metric description')
        elif action == 'Show':
            st.write(pd.DataFrame(sqlite2_polars.view_all_metrics()))
        elif action == 'Delete':
            metrics = sqlite2_polars.view_all_metrics()
            metrics = [x[0] for x in metrics]
            multid_placeholder = col.empty()
            del_list = multid_placeholder.multiselect('Choose metrics to delete', metrics, key='d_multi')
            if st.button('Submit'):
                for metric in del_list:
                    sql_stuff.delete_metric(metric)
                    metrics.remove(metric)
                del_list = multid_placeholder.multiselect('Choose metrics to delete', metrics)
    elif widget == 'headers':
        action = col.selectbox(
            'Actions', ['Show', 'Add', 'Delete', 'Update'])
        col, _, _, _ = visf.create_columns(4, [0,0,0,1])
        if action == 'Add':
            h_placeholder = col.empty()
            h_content = h_placeholder.text_input('Header', key='head_key')
            a_placeholder = col.empty()
            a_content = a_placeholder.text_input('Alias', key='alias_key')
            k_placeholder = col.empty()
            k_content = k_placeholder.text_input('Keyword', key='keywd')
            d_placeholder = col.empty()
            d_content = d_placeholder.text_area('Description', key='description')
            if st.button('Submit'):
                sql_stuff.add_header(h_content, d_content, a_content, k_content)
                h_content = h_placeholder.text_input('Header')
                a_content = a_placeholder.text_input('Alias')
                k_content = k_placeholder.text_input('Keyword')
                d_content = d_placeholder.text_area('Description')
        elif action == 'Delete':
            h_ph = col.empty()
            h_content = h_ph.selectbox('Choose a header to delete',
                sqlite2_polars.ret_all_headers(headings_df,'return'), key='hd_key')
            if st.button('Submit'):
                sql_stuff.delete_header(h_content)
                h_content = h_ph.selectbox('Choose a header to delete',
                    sqlite2_polars.ret_all_headers(headings_df,'return'))

        elif action == 'Show':
            st.write(pd.DataFrame(sqlite2_polars.ret_all_headers(headings_df,'show')))

        elif action == 'Update':
            u_sel_ph = col.empty()
            u_sel = u_sel_ph.selectbox('Choose a header to update',
                sqlite2_polars.ret_all_headers(headings_df,'return'), key='hd_key')
            u_ph = col.empty()
            u_content = u_ph.text_area('Update Header', value=u_sel,)
            a_placeholder = col.empty()
            a_content = a_placeholder.text_input('Alias', key='ualias_key', 
                value=sqlite2_polars.get_header_prop(u_sel, 'alias'))
            k_placeholder = col.empty()
            k_content = k_placeholder.text_input('Keyword', key='ukwd_key', 
                value=sqlite2_polars.get_header_prop(u_sel, 'keywd'))
            d_placeholder = col.empty()
            d_content = d_placeholder.text_input('Description', key='ud_key', 
                value=sqlite2_polars.get_header_prop(u_sel, 'description'))

            if st.button('Submit'):
                sql_stuff.update_header(u_sel, header=u_content, alias=a_content, description=d_content, keyword=k_content)
