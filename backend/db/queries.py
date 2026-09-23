from .connection import get_cursor
from backend.config import ZERO_SHOT_MODEL

def article_exists(identifier):
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM articles WHERE identifier = %s", (identifier,))
        return cur.fetchone() is not None

def insert_article(identifier, source_name, title, url, url_canon,
                    published_utc, snippet, embedding, category=None):
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO articles
                (identifier, source_name, title, url, url_canon,
                 published_utc, snippet, embedding, category, category_model)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (identifier) DO NOTHING
            """,
            (identifier, source_name, title, url, url_canon,
             published_utc, snippet, embedding, category, ZERO_SHOT_MODEL)
        )
        return cur.rowcount