import re
import sql_stuff
import polars as pl
from streamlit import cache_data

@cache_data
def get_table_df(table_name: str):
    data_db = sql_stuff.find_db()
    connection_uri = f"sqlite:///{data_db}"
    query = f"select * from {table_name}"
    df = pl.read_database(query=query, connection=connection_uri)
    return df

def get_col_list_from_filter(df: pl.DataFrame, column: str, filter: str,
       return_column: str) -> list:
    return df.filter(pl.col(column).str.contains(filter))[return_column].to_list()

def get_exact_value_from_filter(df: pl.DataFrame, column: str, filter: str,
       return_column: str) -> any:
    result_series = df[column].eq(filter)
    if result_series.any():
         return df.filter(result_series)[return_column].to_list()[0]
    else:
        return None

@cache_data
def ret_metric_description(metric: str,) -> str:
    df = get_table_df('metric')
    description = f'no description found for {metric}'
    result_series = df['metric'].eq(metric)
    if result_series.any():
        description = df.filter(result_series)['description'].to_list()[0]
    return description

@cache_data
def view_all_metrics() -> list:
    df = get_table_df('metric')
    m_list = []
    values = df.select(['metric', 'description'])
    metric_list = (values['metric'])
    desc_list = (values['description'])
    for x, y in zip(metric_list, desc_list):
        m_list.append([x, y])
    return m_list

def ret_all_headers(df, kind: str ='return'):
    h_list = []
    df = df.select(pl.exclude('id'))
    if kind == 'show':
        x = list(df)
        values = zip(*x)
        for header, description, alias, keywd in values:
            h_list.append([header, description, alias, keywd])
    else:
        for header in df.select('header')['header'].to_list():
            h_list.append(header)
    return h_list

@cache_data
def get_header_prop(header, property):
    # check if exact header is in df
    headings_df = get_table_df('headingstable')
    result_series = headings_df['header'].eq(header)
    if result_series.any():
        property = headings_df.filter(result_series)[property].to_list()[0]
        return property
    # header differs from headers in df
    else:
        header_result_list = []
        all_headers = ret_all_headers(headings_df)
        org_header = header
        org_header_items = org_header.split()
        length_header = len(org_header_items)
        for entry in all_headers:
            # max first 2 metric checks in header
            end_slice =2 if length_header >= 2 else 1
            for metric in org_header_items[0:end_slice]:
                if metric in entry:
                    header_result_list.append(entry)
                    break
        if len(header_result_list) == 1:
            # one header found which differs slightly from original 
            result_series = headings_df['header'].eq(header_result_list[0])
            property = headings_df.filter(result_series)[property].to_list()[0]
            return property
        else:
            # multiple header with same metric, e.g. %usr
            col_field = []
            for header_result in header_result_list:
                counter = 0
                for item in org_header_items:
                    if item in header_result:
                    # count how much different items compared to header
                        counter += 1
                col_field.append([header_result, counter])
            if col_field:
                best_result = max(col_field, key=lambda x: x[1])[0]
                result_series = headings_df['header'].eq(best_result)
                property = headings_df.filter(result_series)[property].to_list()[0]
                return property
            else:
                return org_header

#print(get_header_prop("rxpck/s txpck/s rxkB/s txkB/s rxcmp/s txcmp/s rxmcst/s %ifutil bla", 'description'))

@cache_data
def get_header_from_alias(alias):
    headings_df = get_table_df('headingstable')
    return get_exact_value_from_filter(headings_df, 'alias', alias, 'header')

@cache_data
def get_sub_device_from_header(header):
    headings_df = get_table_df('headingstable')
    ret_search = re.compile(r'(False.*)|(None.*)', re.IGNORECASE)
    keywd =  get_exact_value_from_filter(headings_df, 'header', header, 'keywd')
    if not keywd or ret_search.search(keywd):
        return False
    return keywd