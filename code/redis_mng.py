#!/usr/bin/python3
from streamlit import button as st_button
import redis
import visual_funcs as visf
from config import Config

def get_redis_conn(decode=True):
    connection_params = {
        "host": Config.redis_host,
        "port": Config.redis_port,
        "encoding": "utf-8",
        "decode_responses": decode,
    }
    if Config.redis_user:
        connection_params["username"] = Config.redis_user
    if Config.redis_password:
        connection_params["password"] = Config.redis_password
    try:
        rs = redis.StrictRedis(**connection_params)
        rs.ping()
        return rs
    except:
        # print(
        #     f"Could not connect to Redis server {Config.redis_host}:{Config.redis_port}"
        # )
        return None


rs = get_redis_conn()
# for pickled connections we need connect with decode False
rs_b = get_redis_conn(decode=False)

def show_keys():
    klist = []
    for key in rs.scan_iter('*'):
        klist.append(key)
    return klist

def show_hash_keys(hash):
    return rs.hkeys(hash)

def delete_redis_keys():
    cols = visf.create_columns(4,[0,1,1,1])
    col1 = cols[0]
    hash = col1.selectbox('Select hash', show_keys())
    hash_keys = col1.multiselect('Select n keys', show_hash_keys(hash))
    if st_button('Submit'):
        for hkey in hash_keys:
            rs.hdel(hash, hkey)

def delete_redis_key(rhash, rkey):
    try:
        rs.hdel(rhash, rkey)
    except Exception as e:
        print(f'could not delete {rkey} from {rhash} on Redis server')
        print(f'Exception: {e}')

def redis_tasks(col):
    cols = visf.create_columns(4,[0,1,1,1])
    col1 = cols[0]
    redis_actions = ['Delete Redis Keys']
    r_ph = col1.empty()
    redis_sel = r_ph.selectbox('Redis Tasks', redis_actions, key="m_redis")
    if redis_sel == 'Delete Redis Keys':
        delete_redis_keys()
    redis_sel = r_ph.selectbox('Redis Tasks', redis_actions, default=None, key="m_redis")

def get_redis_val(rkey, decode=False, property=None):
    rs = get_redis_conn(decode=decode)
    if not rs:
        return None
    if property:
        try:
            return rs.hget(rkey, property)
        except:
            return None
    else:
        try:
            return rs.get(rkey)
        except:
            return None

def set_redis_key(data, rkey, property=None, decode=False):
    """data -> dict or value
       key_pref, e.g user
       key, e.g jschaef -> compounds to user:jschaef
       bytes -> None or something, sets decode to False
    """
    rs = get_redis_conn(decode=decode)
    if not rs:
        return None

    try:
        t_dict = {property:data}
        rs.hset(rkey, mapping=t_dict)
    except Exception as e:
        print(f'Could not write {rkey}, {e}')

def del_redis_key_property(rkey, property, decode=False):
    rs = get_redis_conn(decode=decode)
    if not rs:
        return None
    if rs.exists(rkey, property):
        rs.hdel(rkey, property)

def show_redis_hash_keys(rkey):
    rs = get_redis_conn()
    if not rs:
        return None
    return rs.hkeys(rkey)

def convert_df_for_redis(df):
    return df.to_pandas().to_parquet()