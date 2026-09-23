import psycopg2
import os
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

DB_CONFIG = {
    "dbname": "articles",
    "user": "postgres",
    "password": os.environ.get("DB_PASSWORD", ""),
    "host": "localhost",
    "port": "5432"
}

@contextmanager
def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@contextmanager
def get_cursor():
    with get_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
        finally:
            cursor.close()