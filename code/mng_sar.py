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
                for multi_files in sar_files:
                    for u_file in multi_files:
                        if u_file is not None:
                            #st.write(dir(sar_file))
                            f_check = Magic()
                            #stringio = io.StringIO(sar_file.decode("utf-8"))
                            bytes_data = u_file.read()
                            res = f_check.from_buffer(bytes_data)
                            
                            # Enhanced detection: check both magic result and binary patterns
                            is_openpgp_detected = "OpenPGP Secret Key" in res
                            is_generic_data = "data" in res.lower()
                            is_binary_sar = is_sar_binary_file(bytes_data, u_file.name)
                            
                            print(f"File: {u_file.name}")
                            print(f"Magic result: '{res}'")
                            print(f"Binary SAR detection: {is_binary_sar}")
                            
                            # Check if it's a binary SAR file that needs conversion
                            if is_openpgp_detected or (is_generic_data and is_binary_sar):
                                conversion_reason = "OpenPGP Secret Key" if is_openpgp_detected else "Binary SAR file"
                                col1.info(f"Detected {conversion_reason}: {u_file.name}. Converting to ASCII format...")
                                converted_data, new_filename = convert_openpgp_sar_file(bytes_data, u_file.name)
                                
                                if converted_data is not None:
                                    col1.success(f"Successfully converted {u_file.name} to {new_filename}")
                                    bytes_data = converted_data
                                    # Update the filename for processing
                                    u_file.name = new_filename
                                    
                                    # Re-check the converted file
                                    res = f_check.from_buffer(bytes_data)
                                    print(f"After conversion: '{res}'")
                                else:
                                    col1.error(f"Failed to convert {u_file.name}. Skipping file.")
                                    continue
                            if "ASCII text" not in res:
                                col1.warning(
                                    f"""File is not a valid sar ASCII data file. Instead {res}.
                                    If you attempted to upload a binary sar file, please convert it to ASCII format first with the command:\
                                    {convert_cmd}""")
                                continue
                            else:
                                #TODO check if Linux Header is present and if sar 
                                # sections are present
                                col1.write(
                                    f"Sar file is valid. Renaming {u_file.name}")
                                with open(f'{upload_dir}/{u_file.name}', 'wb') as targetf:
                                    targetf.write(bytes_data)
                                #remove name
                                col1, _ = visf.create_columns(2,[0,1])
                                renamed_name = helpers.rename_sar_file(f'{upload_dir}/{u_file.name}', col=col1)
                                
                                # Clean up existing Redis cache entries for this file
                                try:
                                    rkey = f"{Config.rkey_pref}:{username}"
                                    # Get just the basename and construct Redis property key
                                    basename = renamed_name.split("/")[-1]  # Get just filename without path
                                    r_item = f'{basename}_parquet'  # Construct Redis property key
                                    print(f'Cleaning up Redis cache for {rkey}, {r_item} at {datetime.now().strftime("%m/%d/%y %H:%M:%S")}')
                                    redis_mng.del_redis_key_property(rkey, r_item)
                                except Exception as e:
                                    print(f'Could not clean Redis cache for {rkey}, {r_item}: {e}')
                                
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
