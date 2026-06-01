"""本地 Parquet 存储层：幂等读写 + 去重。"""
import os
import pandas as pd

import config

os.makedirs(config.DATA_DIR, exist_ok=True)


def _path(name):
    return os.path.join(config.DATA_DIR, f"{name}.parquet")


def load(name):
    """读取表；不存在返回空 DataFrame。"""
    p = _path(name)
    if os.path.exists(p):
        return pd.read_parquet(p)
    return pd.DataFrame()


def save(name, df):
    df.to_parquet(_path(name), index=False)


def upsert_by_key(name, df_new, key):
    """按主键 upsert：新数据覆盖同键旧数据。key 可为 str 或 list。"""
    keys = [key] if isinstance(key, str) else list(key)
    old = load(name)
    if old.empty:
        merged = df_new.copy()
    else:
        mask = ~old.set_index(keys).index.isin(df_new.set_index(keys).index)
        merged = pd.concat([old.loc[mask], df_new], ignore_index=True)
    save(name, merged)
    return merged


def append_dedup(name, df_new, key):
    """仅追加主键不存在的新行（用于 staking_rewards 按 bill_id 去重）。"""
    old = load(name)
    if old.empty:
        save(name, df_new)
        return df_new
    existing = set(old[key].astype(str))
    add = df_new[~df_new[key].astype(str).isin(existing)]
    merged = pd.concat([old, add], ignore_index=True)
    save(name, merged)
    return merged
