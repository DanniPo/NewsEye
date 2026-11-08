"""Every read the API makes, through a read-only database session.

The API serves results the pipeline has already stored; the passive and active
tiers and the people batch do all the writing. Each connection is opened with
default_transaction_read_only, so PostgreSQL itself refuses a write even if a
bug attempts one, and with a statement timeout so one slow query cannot hold a
request. A database role with SELECT rights only is the next step for a hosted
deployment, where the API should not share the pipeline's credentials.

The tests replace Store with a fake, so they need no database.
"""
import re
import threading
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import PoolError, ThreadedConnectionPool

from backend.analysis.divergence import differences
from backend.config import CLUSTER_MIN_COHERENCE
from backend.db.connection import DB_CONFIG
from backend.scripts.build_site import plain

# every statement in a read-only transaction, and none allowed to run past 5 s
READ_ONLY = "-c default_transaction_read_only=on -c statement_timeout=5000"
# the search cut-off the static site uses: cosine similarity of at least 0.25
MIN_SIMILARITY = 0.25

STORY_SQL = """
    SELECT c.id, c.topic_label, c.article_count, c.coherence, c.clustered_at,
           count(DISTINCT a.source_name) AS outlet_count,
           array_agg(DISTINCT a.source_name ORDER BY a.source_name) AS outlets,
           max(a.published_utc) AS latest,
           (array_agg(a.title ORDER BY a.published_utc DESC NULLS LAST))[1] AS latest_title
    FROM clusters c
    JOIN cluster_members cm ON cm.cluster_id = c.id
    JOIN articles a ON a.id = cm.article_id
    WHERE c.coherence >= %(floor)s
    GROUP BY c.id
    HAVING count(DISTINCT a.source_name) >= %(min_outlets)s
"""


class DatabaseUnavailable(Exception):
    """The database could not be reached. The API answers 503."""


class NotBuilt(Exception):
    """A batch result the API serves has not been built yet. The API answers 503."""


class NotPublished(Exception):
    """The story exists but is too loose to compare, so it gets no page (DEF-23)."""


def clean(text):
    """A feed snippet as plain text: five outlets send theirs as HTML (DEF-39)."""
    return re.sub(r"\s+", " ", plain(text)).strip() if text else text


def _status(row):
    if row.get("sources_used") is not None:
        return "analysed"
    return "headline only" if row.get("title_summary") else "not analysed"


def _readability(stored):
    """Which outlets could be read on the last analysis, or None if not recorded.

    Stored analyses from before 23 October 2026 lack the flags; for those the
    API says so rather than guessing, since a guess could present an unread
    outlet as one that left facts out (NFR-04).
    """
    if not stored:
        return {"recorded": False, "readable_outlets": None, "unread_outlets": None}, {}
    fetched = {a.get("url"): bool(a.get("fetched")) for a in stored}
    readable = {a["source"] for a in stored if a.get("fetched")}
    unread = {a["source"] for a in stored if not a.get("fetched")} - readable
    return ({"recorded": True, "readable_outlets": sorted(readable),
             "unread_outlets": sorted(unread)}, fetched)


class Store:
    def __init__(self, max_connections=8):
        self._pool = None
        self._lock = threading.Lock()
        self._max = max_connections

    def _get_pool(self):
        with self._lock:
            if self._pool is None:
                try:
                    self._pool = ThreadedConnectionPool(1, self._max, options=READ_ONLY,
                                                        **DB_CONFIG)
                except psycopg2.OperationalError as exc:
                    raise DatabaseUnavailable from exc
            return self._pool

    @contextmanager
    def cursor(self):
        pool = self._get_pool()
        try:
            conn = pool.getconn()
        except (psycopg2.OperationalError, PoolError) as exc:
            raise DatabaseUnavailable from exc
        broken = False
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            broken = True
            raise DatabaseUnavailable from exc
        finally:
            if not broken:
                try:
                    conn.rollback()          # read-only: there is never anything to commit
                except psycopg2.Error:
                    broken = True
            pool.putconn(conn, close=broken)

    # ------------------------------------------------------------------ reads
    def health(self):
        with self.cursor() as cur:
            cur.execute("""
                SELECT (SELECT count(*) FROM articles) AS articles,
                       (SELECT count(*) FROM clusters) AS stories,
                       (SELECT count(*) FROM cluster_analysis
                         WHERE sources_used IS NOT NULL) AS analysed,
                       (SELECT max(inserted_at_utc) FROM articles) AS last_article,
                       (SELECT max(clustered_at) FROM clusters) AS last_clustered,
                       to_regclass('people') IS NOT NULL AS people_table
            """)
            row = dict(cur.fetchone())
            people = None
            if row.pop("people_table"):
                cur.execute("SELECT count(*) AS n FROM people")
                people = cur.fetchone()["n"]
        return {**row, "people": people}

    def stories(self, limit, offset, min_outlets):
        """(total, one page of stories) in the dashboard's order: most outlets first."""
        params = {"floor": CLUSTER_MIN_COHERENCE, "min_outlets": min_outlets,
                  "limit": limit, "offset": offset}
        with self.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM ({STORY_SQL}) s", params)
            total = cur.fetchone()["n"]
            cur.execute(f"""
                SELECT s.*, ca.title_summary, ca.sources_used, ca.analyzed_at,
                       ca.consensus, ca.figure_digest, ca.quotes, ca.framing
                FROM ({STORY_SQL}) s
                LEFT JOIN cluster_analysis ca ON ca.cluster_id = s.id
                ORDER BY s.outlet_count DESC, s.article_count DESC, s.id
                LIMIT %(limit)s OFFSET %(offset)s
            """, params)
            rows = cur.fetchall()
        return total, [{
            "id": r["id"], "headline": r["title_summary"] or r["latest_title"],
            "topic": r["topic_label"], "outlets": r["outlets"],
            "article_count": r["article_count"], "coherence": r["coherence"],
            "latest": r["latest"], "status": _status(r), "analysed_at": r["analyzed_at"],
            "differences": differences(r) if r["sources_used"] is not None else None,
        } for r in rows]

    def story(self, story_id):
        """One story page's data, or None if there is no such story."""
        with self.cursor() as cur:
            cur.execute("""
                SELECT c.id, c.topic_label, c.article_count, c.coherence, c.clustered_at,
                       ca.title_summary, ca.subject, ca.sources_used, ca.analyzed_at,
                       ca.consensus, ca.figure_digest, ca.quotes, ca.framing,
                       ca.articles AS read_articles
                FROM clusters c
                LEFT JOIN cluster_analysis ca ON ca.cluster_id = c.id
                WHERE c.id = %s
            """, (story_id,))
            row = cur.fetchone()
            if row is None:
                return None
            if row["coherence"] is not None and row["coherence"] < CLUSTER_MIN_COHERENCE:
                raise NotPublished(story_id)
            cur.execute("""
                SELECT a.id, a.source_name, a.title, a.url, a.published_utc, a.snippet,
                       a.category
                FROM cluster_members cm
                JOIN articles a ON a.id = cm.article_id
                WHERE cm.cluster_id = %s
                ORDER BY a.published_utc DESC NULLS LAST, a.id
            """, (story_id,))
            members = cur.fetchall()
        readability, fetched = _readability(row["read_articles"])
        analysed = row["sources_used"] is not None
        return {
            "id": row["id"],
            "headline": row["title_summary"] or (members[0]["title"] if members else None),
            "topic": row["topic_label"], "subject": row["subject"],
            "coherence": row["coherence"], "article_count": row["article_count"],
            "outlets": sorted({m["source_name"] for m in members}),
            "clustered_at": row["clustered_at"], "status": _status(row),
            "analysed_at": row["analyzed_at"], "readability": readability,
            "articles": [{"id": m["id"], "outlet": m["source_name"], "title": m["title"],
                          "url": m["url"], "published": m["published_utc"],
                          "snippet": clean(m["snippet"]),
                          # None: this article was not part of the last analysis
                          "readable": fetched.get(m["url"])} for m in members],
            "analysis": {
                "coverage": row["consensus"] or [], "quotes": row["quotes"] or [],
                "figures": row["figure_digest"] or [], "framing": row["framing"] or [],
                "differences": differences(row),
            } if analysed else None,
        }

    def search(self, query, limit):
        """Articles closest in meaning to the query, each with its story if it has one."""
        # imported here: loading MiniLM takes seconds, and only search needs it
        from backend.nlp.search import embed_query
        vector = embed_query(query)
        with self.cursor() as cur:
            cur.execute("""
                SELECT a.id, a.title, a.source_name, a.url, a.published_utc, a.snippet,
                       cm.cluster_id, 1 - (a.embedding <=> %(v)s::vector) AS similarity
                FROM articles a
                LEFT JOIN cluster_members cm ON cm.article_id = a.id
                WHERE a.embedding IS NOT NULL
                ORDER BY a.embedding <=> %(v)s::vector
                LIMIT %(limit)s
            """, {"v": vector, "limit": limit})
            rows = cur.fetchall()
        return [{"id": r["id"], "title": r["title"], "outlet": r["source_name"],
                 "url": r["url"], "published": r["published_utc"],
                 "snippet": clean(r["snippet"]), "story_id": r["cluster_id"],
                 "similarity": round(float(r["similarity"]), 3)}
                for r in rows if r["similarity"] >= MIN_SIMILARITY]

    def _require_people(self, cur):
        cur.execute("SELECT to_regclass('people') IS NOT NULL AS ok")
        if not cur.fetchone()["ok"]:
            raise NotBuilt("People pages have not been built: run python -m backend.people")

    def people(self):
        with self.cursor() as cur:
            self._require_people(cur)
            cur.execute("""
                SELECT id, name, articles, built_at,
                       (SELECT count(*) FROM jsonb_object_keys(outlets)) AS outlets
                FROM people ORDER BY articles DESC, name
            """)
            rows = cur.fetchall()
        if not rows:
            raise NotBuilt("People pages have not been built: run python -m backend.people")
        return [dict(r) for r in rows]

    def person(self, person_id, records=20):
        """One person, with each outlet's newest `records` mentions and the total.

        Every mention is stored, but a person named 600 times makes a 600 KB
        page; the static site shows six per outlet."""
        with self.cursor() as cur:
            self._require_people(cur)
            cur.execute("SELECT * FROM people WHERE id = %s", (person_id,))
            row = cur.fetchone()
        if row is None:
            return None
        person = dict(row)
        person["outlets"] = {outlet: {**summary,
                                      "records_total": len(summary.get("records", [])),
                                      "records": summary.get("records", [])[:records]}
                             for outlet, summary in person["outlets"].items()}
        return person
