#!/usr/bin/python3
import os
import pandas as pd
import streamlit as st
from magic import Magic
from datetime import datetime
import subprocess
import tempfile
import redis_mng
import helpers_pl as helpers
from config import Config
import visual_funcs as visf


def is_sar_binary_file(file_content: bytes, filename: str) -> bool:
    """
    Detect if a file is a binary SAR file using multiple methods.
    
    Args:
        file_content: Raw bytes of the file
        filename: Original filename
    
    Returns:
        bool: True if detected as binary SAR file
    """
    if len(file_content) < 50:
        return False
    
    # Method 1: Check filename patterns (SAR files often start with 'sa' followed by date)
    filename_lower = filename.lower()
    has_sar_filename = (
        filename_lower.startswith('sa') and 
        len(filename) >= 10 and 
        filename[2:].isdigit()  # sa followed by digits (date)
    )
    
    # Method 2: Check for binary characteristics
    first_100 = file_content[:100]
    
    # Count non-printable characters (excluding common whitespace)
    non_printable_count = sum(1 for b in first_100 
                             if b < 32 and b not in [9, 10, 13])  # exclude tab, LF, CR
    
    # If more than 20% of first 100 bytes are non-printable, likely binary
    is_mostly_binary = non_printable_count > 20
    
    # Method 3: Check for common SAR binary patterns
    has_binary_patterns = (
        file_content[:4] == b'\x00\x00\x00\x00' or  # Common null pattern
        file_content[0:1] in [b'\x00', b'\x01', b'\x02', b'\x03'] or  # Binary start bytes
        b'\x00\x00' in file_content[:50] or  # Embedded nulls
        all(b != 0 and (b < 32 or b > 126) for b in file_content[10:30])  # Non-ASCII range
    )
    
    # Method 4: Try to decode as text - if it fails, likely binary
    try:
        file_content[:200].decode('utf-8')
        is_decodable = True
    except UnicodeDecodeError:
        is_decodable = False
    
    # Method 5: Check for SAR-specific signatures (additional indicator)
    has_sar_signatures = (
        b'SYSSTAT' in file_content[:500] or
        b'Linux' in file_content[:200]
    )
    
    # Decision logic: combine multiple indicators
    binary_indicators = sum([
        has_sar_filename,
        is_mostly_binary,
        has_binary_patterns,
        not is_decodable,
        has_sar_signatures,  # Added this to the decision
    ])
    
    # If we have 2 or more strong indicators, treat as binary SAR
    return binary_indicators >= 2


def convert_openpgp_sar_file(file_content: bytes, original_filename: str) -> tuple[bytes, str]:
    """
    Convert OpenPGP Secret Key SAR file to ASCII format using sar command.
    
    Args:
        file_content: Raw bytes of the uploaded file
        original_filename: Original filename (e.g., 'sa20250726')
    
    Returns:
        tuple: (converted_bytes_data, new_filename) or (None, None) if conversion failed
    """
    try:
        # Generate output filename: sa20250726 -> sar20250726
        if original_filename.startswith('sa') and len(original_filename) >= 10:
            new_filename = 'sar' + original_filename[2:]
        else:
            new_filename = f"sar_{original_filename}"
        
        # Create temporary file for input
        with tempfile.NamedTemporaryFile(delete=False, suffix='_input') as temp_input:
            temp_input.write(file_content)
            temp_input_path = temp_input.name
        
        # Run the sar conversion command
        # Use shell=True to handle the unset LANG part properly
        full_cmd = f"unset LANG; sar -A -t -f {temp_input_path}"
        
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=False  # We want bytes output
        )
        
        if result.returncode == 0:
            # Read the converted output as bytes
            converted_data = result.stdout
            
            # Clean up temporary file
            os.unlink(temp_input_path)
            
            return converted_data, new_filename
        else:
            # Clean up temporary file on error
            os.unlink(temp_input_path)
            
            print(f"SAR conversion failed: {result.stderr.decode()}")
            return None, None
            
    except Exception as e:
        print(f"Error during SAR conversion: {e}")
        return None, None


def nav_to_overview():
    st.session_state['nav_top'] = "Analyze Data"
    st.session_state['nav_analysis'] = "Graphical Overview"
    st.session_state['upload_success'] = False # Reset flag

def nav_to_multi():
    st.session_state['nav_top'] = "Analyze Data"
    st.session_state['nav_analysis'] = "Multiple Sar Files"
    st.session_state['upload_success'] = False # Reset flag

def file_mng(upload_dir: str, username:str):
    col1, _, _, _ = visf.create_columns(4,[0,1,1,1])
    manage_files = ['Show Sar Files','Add Sar Files', 'Delete Sar Files']
    sar_files = [ x for x in os.listdir(upload_dir) if os.path.isfile(f'{upload_dir}/{x}')]
    file_size = [os.path.getsize(f'{upload_dir}/{x}') for x in sar_files]
    # Separate ASCII SAR files from parquet files
    sar_files_uploaded = [x for x in sar_files if not x.endswith(('.parquet'))]
    sar_files_parquet = [x.replace('.parquet', '') for x in sar_files if x.endswith('.parquet')]
    sar_files = sar_files_parquet + sar_files_uploaded

    managef_options = col1.selectbox(
        'Show/Add/Delete', manage_files)

    st.markdown('___')
    if managef_options == 'Add Sar Files':
        upload_hint = "SAR files must be in Posix format, decimal seperator has to be '.'. OpenPGP Secret Key files (binary SAR files) will be automatically converted."
        convert_cmd = "```unset LANG; sar -A -t -f <binary_file> > <ascii_file>```"
        sar_convert_hint = f"""{upload_hint} \
        \nManual conversion command: {convert_cmd}"""
        sar_files = [col1.file_uploader(
            "Please upload your SAR files", key='sar_uploader',
            accept_multiple_files=True, help=sar_convert_hint,)]
        
        if col1.button('Submit'):
            if sar_files:
                upload_count = 0
                for multi_files in sar_files:
                    for u_file in multi_files:
                        if u_file is not None:
                            f_check = Magic()
                            bytes_data = u_file.read()
                            res = f_check.from_buffer(bytes_data)
                            
                            is_openpgp_detected = "OpenPGP Secret Key" in res
                            is_generic_data = "data" in res.lower()
                            is_binary_sar = is_sar_binary_file(bytes_data, u_file.name)
                            
                            if is_openpgp_detected or (is_generic_data and is_binary_sar):
                                converted_data, new_filename = convert_openpgp_sar_file(bytes_data, u_file.name)
                                if converted_data is not None:
                                    bytes_data = converted_data
                                    u_file.name = new_filename
                                    res = f_check.from_buffer(bytes_data)
                                else:
                                    col1.error(f"Failed to convert {u_file.name}.")
                                    continue
                            
                            if "ASCII text" in res:
                                with open(f'{upload_dir}/{u_file.name}', 'wb') as targetf:
                                    targetf.write(bytes_data)
                                renamed_name = helpers.rename_sar_file(f'{upload_dir}/{u_file.name}', col=None)
                                upload_count += 1
                                
                                try:
                                    rkey = f"{Config.rkey_pref}:{username}"
                                    basename = renamed_name.split("/")[-1]
                                    redis_mng.del_redis_key_property(rkey, f'{basename}_parquet')
                                except: pass
                
                if upload_count > 0:
                    st.session_state['upload_success'] = True
                    st.rerun()

        # Show navigation buttons outside the 'if Submit' block
        if st.session_state.get('upload_success'):
            st.success("Files uploaded and processed successfully!")
            st.markdown('### Next Steps')
            b_col1, b_col2 = st.columns(2)
            b_col1.button("Go to Graphical Overview 📊", on_click=nav_to_overview)
            b_col2.button("Go to Multiple Sar Files 📂", on_click=nav_to_multi)
                                
    elif managef_options == 'Delete Sar Files':
        if sar_files:
            dfiles_ph = col1.empty()
            dfiles = dfiles_ph.multiselect(
                'Choose your Files to delete', sar_files)
            if col1.button('Delete selected Files'):
                for file in dfiles:
                    # Construct Redis property key correctly: basename + "_parquet"
                    r_item = f'{file}_parquet'  # file already contains the basename without .parquet extension
                    df_file = f'{upload_dir}/{file}.parquet'
                    fs_file = f'{upload_dir}/{file}'
                    os.system(f'rm -f {df_file}')
                    os.system(f'rm -f {fs_file}')
                    try:
                        rkey = f"{Config.rkey_pref}:{username}"
                        print(
                            f'delete {rkey}, {r_item} from redis at {datetime.now().strftime("%m/%d/%y %H:%M:%S")}')
                        redis_mng.del_redis_key_property(rkey, r_item)
                    except Exception as e:
                        print(f'{rkey}, {r_item} not available in redis db or redis \
                            db not online, exception  is {e}')

                sar_files = os.listdir(upload_dir)
                # Update file list to reflect current state after deletion
                sar_files_uploaded = [x for x in sar_files if not x.endswith(('.parquet'))]
                sar_files_parquet = [x.replace('.parquet', '') for x in sar_files if x.endswith('.parquet')]
                sar_files = sar_files_parquet + sar_files_uploaded
                dfiles = dfiles_ph.multiselect(
                    'Choose your Files to delete', sar_files, default=None)
        else:
            col1.write("You currently have no sar files")

    elif managef_options == 'Show Sar Files':
        col1.empty()
        fsize = [f'{round(x/1024/1024,2)} MB' for x in file_size]
        col1.write(pd.DataFrame({'Files':sar_files, 'Size':fsize}))
