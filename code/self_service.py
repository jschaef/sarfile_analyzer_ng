#!/usr/bin/python3
import os
import streamlit as st
import sql_stuff
import pandas as pd
import visual_funcs as visf
import handle_user_status
from config import Config

def self_service(username):
    cols = visf.create_columns(4, [0,1,1,1])
    col1 = cols[0]
    menu_items = ['Password Change']
    choice = col1.selectbox('Take your Choice',menu_items)
    if choice == 'Password Change':
        col1.header('Change your Password')
        password = col1.text_input("Type your new password:", type='password')
        re_password = col1.text_input("Retype your new password:", type='password')
        if st.button('Submit'):
            if password == re_password and password:
                sql_stuff.change_password(username, password)
                col1.info('Your Password has been Changed')
            elif not password:
                col1.warning("empty password is not allowed")
            else:
                col1.warning("your password does not match")

def admin_service():
    cols = visf.create_columns(4, [0,1,1,1])
    col1 = cols[0]
    col1.header('User Management')
    menu_items = ['Show Users', 'User Password Change', 'Roles Management', 
        'Delete User', 'Login History']
    choice = col1.selectbox('Take your Choice',menu_items)
    if choice == 'Show Users':
         col1.write(pd.DataFrame(sql_stuff.view_all_users('show'), columns=["Username", "Role"]))    
    else:
        user_ph = col1.empty()
        user = user_ph.selectbox('Choose User', sql_stuff.view_all_users(kind=None))
    if choice == 'User Password Change':
        col1.subheader(f'Change Password of {user}')
        password = col1.text_input("Type the new password:", type='password')
        re_password = col1.text_input("Retype your new password:", type='password')
        if st.button('Submit'):
            if password == re_password and password:
                sql_stuff.change_password(user, password)
                col1.info(f'Password of {user} has been Changed')
            elif not password:
                col1.warning("empty password is not allowed")
            else:
                col1.warning("The passwords do not match") 
    elif choice == 'Roles Management':
        col1.subheader(f'Change Role of {user}')
        r_content = col1.selectbox('Choose role', sql_stuff.ret_all_roles())
        if st.button('Submit'):
            sql_stuff.modify_user(user, r_content)
            col1.info(f'Role {r_content} for {user} has been set')
    elif choice == 'Delete User':
        upload_dir = f'{Config.upload_dir}/{user}'
        col1.subheader(f'Delete User {user}')
        if st.button('Submit'):
            sql_stuff.delete_user(user)
            if user in upload_dir:
                os.system(f'rm -rf {upload_dir}')
            col1.info(f'User {user} has been deleted')
    elif choice == 'Login History':
        user_ph.empty()
        col1.subheader('Show Login times for users')
        df_pl = handle_user_status.get_user_status_df()
        df = df_pl.to_pandas().set_index('login_time')
        col1.dataframe(df)
        del_help = 'Delete all login times older than the chosen date'
        if col1.checkbox('Delete Login Times', help=del_help):
            delete_date = col1.date_input('Choose Date', value=None, min_value=None, max_value=None, key=None)
            if col1.button('Delete'):
                result = handle_user_status.remove_old_logins(df_pl, delete_date)
                if not result.is_empty():
                    handle_user_status.write_df_to_file(result)
                    col1.info(f'''Records older than {delete_date} 
                        have been deleted''')
                    col1.write('Remaining Records:')
                    col1.write(result.to_pandas().set_index('login_time'))
                else:
                    df_pl = handle_user_status.create_user_status_df()
                    handle_user_status.write_df_to_file(df_pl)
