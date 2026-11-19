import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    # DB_NAME points every stage at another database, e.g. a copy for testing
    "dbname": os.environ.get("DB_NAME", "articles"),
    # the defaults are a local PostgreSQL; a server (deploy/) or another install
    # sets DB_USER, DB_HOST and DB_PORT instead
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432"),
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