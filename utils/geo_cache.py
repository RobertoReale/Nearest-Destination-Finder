import sqlite3
import os
import json
import sys

_DB_NAME = ".geo_cache_test.db" if "pytest" in sys.modules else ".geo_cache.db"
_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), _DB_NAME)

def _get_conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS geocode (address TEXT PRIMARY KEY, coords TEXT)")
    conn.commit()
    return conn

def get_cached_coords(address: str):
    try:
        with _get_conn() as conn:
            cursor = conn.execute("SELECT coords FROM geocode WHERE address=?", (address,))
            row = cursor.fetchone()
            if row:
                return tuple(json.loads(row[0]))
    except Exception:
        pass
    return None

def set_cached_coords(address: str, coords):
    if coords is None:
        return
    try:
        with _get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO geocode (address, coords) VALUES (?, ?)", 
                         (address, json.dumps(coords)))
            conn.commit()
    except Exception:
        pass
