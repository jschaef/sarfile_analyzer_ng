#!/usr/bin/python3
from streamlit import button as st_button
import redis
import visual_funcs as visf
from config import Config
import logging

# Module-level cache for Redis connections and status
_redis_cache = {}
_redis_disabled = False

def get_redis_conn(decode=True):
    global _redis_disabled
    
    if _redis_disabled:
        return None
        
    cache_key = f"conn_{decode}"
    if cache_key in _redis_cache:
        return _redis_cache[cache_key]

    connection_params = {
        "host": Config.redis_host,
        "port": Config.redis_port,
        "encoding": "utf-8",
        "decode_responses": decode,
        "socket_timeout": 1.0,           # Fast failure if Redis is down
        "socket_connect_timeout": 1.0,   # Fast failure if Redis is down
        "retry_on_timeout": False,
    }
    if Config.redis_user:
        connection_params["username"] = Config.redis_user
    if Config.redis_password:
        connection_params["password"] = Config.redis_password
        
    try:
        rs = redis.StrictRedis(**connection_params)
        # We avoid rs.ping() here because it's synchronous and slow.
        # The connection will fail on the first actual operation if Redis is down.
        _redis_cache[cache_key] = rs
        return rs
    except Exception:
        _redis_disabled = True
        return None

# for pickled connections we need connect with decode False
def get_rs():
    return get_redis_conn(decode=True)

def get_rs_b():
    return get_redis_conn(decode=False)

def show_keys():
    rs = get_rs()
    if not rs: return []
    klist = []
    try:
        for key in rs.scan_iter('*'):
            klist.append(key)
    except Exception:
        pass
    return klist

def show_hash_keys(hash):
    rs = get_rs()
    if not rs: return []
    try:
        return rs.hkeys(hash)
    except Exception:
        return []

def delete_redis_keys():
    rs = get_rs()
    if not rs: return
    cols = visf.create_columns(4,[0,1,1,1])
    col1 = cols[0]
    hash = col1.selectbox('Select hash', show_keys())
    hash_keys = col1.multiselect('Select n keys', show_hash_keys(hash))
    if st_button('Submit'):
        try:
            for hkey in hash_keys:
                rs.hdel(hash, hkey)
        except Exception:
            pass

def redis_tasks(col):
    cols = visf.create_columns(4,[0,1,1,1])
    col1 = cols[0]
    redis_actions = ['Delete Redis Keys']
    r_ph = col1.empty()
    redis_sel = r_ph.selectbox('Redis Tasks', redis_actions, key="m_redis")
    if redis_sel == 'Delete Redis Keys':
        delete_redis_keys()

def get_redis_val(rkey, decode=False, property=None):
    rs = get_redis_conn(decode=decode)
    if not rs:
        return None
    try:
        if property:
            return rs.hget(rkey, property)
        else:
            return rs.get(rkey)
    except Exception:
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
        if property:
            t_dict = {property:data}
            rs.hset(rkey, mapping=t_dict)
        else:
            rs.set(rkey, data)
    except Exception as e:
        pass

def del_redis_key_property(rkey, property, decode=False):
    rs = get_redis_conn(decode=decode)
    if not rs:
        return None
    try:
        if rs.hexists(rkey, property):
            rs.hdel(rkey, property)
    except Exception:
        pass

def convert_df_for_redis(df):
    return df.to_pandas().to_parquet()
