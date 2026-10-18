from backend.config import ZERO_SHOT_MODEL

from .connection import get_cursor


def existing_identifiers(identifiers):
    """The subset of identifiers already stored, in one query.

    Ingest used to check each feed item with its own query. Every query opened
    its own connection, and a password handshake to Postgres costs ~125ms, so
    re-reading 12 feeds spent 24s just confirming items it already had.
    """
    if not identifiers:
        return set()
    with get_cursor() as cur:
        cur.execute("SELECT identifier FROM articles WHERE identifier = ANY(%s)",
                    (list(identifiers),))
        return {row["identifier"] for row in cur.fetchall()}

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