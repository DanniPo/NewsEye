"""Every read the API makes, through a read-only database session.

The API serves results the pipeline has already stored; the passive and active
tiers and the people batch do all the writing. Each connection is opened with
default_transaction_read_only, so PostgreSQL itself refuses a write even if a
bug attempts one, and with a statement timeout so one slow query cannot hold a
request. A database role with SELECT rights only is the next step for a hosted
deployment, where the API should not share the pipeline's credentials.

The tests replace Store with a fake, so they need no database.
"""
import logging
import os
import re
import threading
from collections import Counter
from contextlib import contextmanager
from urllib.parse import urlsplit

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import PoolError, ThreadedConnectionPool

from backend.analysis.contention import LISTED, contention
from backend.analysis.digest import cited_authority, digest_groups, summarise
from backend.analysis.divergence import differences
from backend.analysis.verbs import family_of
from backend.config import CLUSTER_MIN_COHERENCE, FALLBACK_LABEL, RSS_FEEDS
from backend.db.connection import DB_CONFIG
from backend.scripts.build_site import (
    STATE_MEDIA,
    VERB_TONE,
    gaps_in,
    headline_tense,
    overall_title,
    overall_tone,
    plain,
)

log = logging.getLogger("newseye.api")

# every statement in a read-only transaction, and none allowed to run past 5 s
READ_ONLY = "-c default_transaction_read_only=on -c statement_timeout=5000"
# the search cut-off the static site uses: cosine similarity of at least 0.25
MIN_SIMILARITY = 0.25

# Published stories: coherent enough to compare and covered by min_outlets
# outlets. topic and source narrow the list; both are values, never SQL.
STORY_SQL = """
    SELECT c.id, c.topic_label, c.article_count, c.coherence, c.clustered_at,
           count(DISTINCT a.source_name) AS outlet_count,
           array_agg(DISTINCT a.source_name ORDER BY a.source_name) AS outlets,
           max(a.published_utc) AS latest,
           array_agg(a.title) AS titles,
           -- the story page's order, ties included, so a card and its page show
           -- the same headline before the story has a summary one
           (array_agg(a.title ORDER BY a.published_utc DESC NULLS LAST, a.id))[1] AS latest_title
    FROM clusters c
    JOIN cluster_members cm ON cm.cluster_id = c.id
    JOIN articles a ON a.id = cm.article_id
    WHERE c.coherence >= %(floor)s
      AND (%(topic)s::text IS NULL OR coalesce(c.topic_label, 'General') = %(topic)s)
    GROUP BY c.id
    HAVING count(DISTINCT a.source_name) >= %(min_outlets)s
       AND (%(source)s::text IS NULL OR bool_or(a.source_name = %(source)s))
"""


def story_params(**values):
    """STORY_SQL's parameters: every published story unless values narrow it."""
    return {"floor": CLUSTER_MIN_COHERENCE, "min_outlets": 2, "topic": None, "source": None,
            **values}


def slug(name):
    """'The Kenya Times' -> 'the-kenya-times': an outlet's name in a link."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# The configured feeds, not DISTINCT source_name: the articles table still holds
# rows under "| Daily Nation", a malformed name from an earlier feed list.
SOURCES = {slug(feed["name"]): feed["name"] for feed in RSS_FEEDS}
WEBSITES = {feed["name"]: "{0.scheme}://{0.netloc}".format(urlsplit(feed["rss_url"]))
            for feed in RSS_FEEDS}
# a source page shows this many of an outlet's topics; the list shows the top few
SOURCE_TOPICS_LISTED = 3
# what a story card needs from a stored analysis
CARD_COLUMNS = """ca.title_summary, ca.sources_used, ca.analyzed_at, ca.consensus,
                  ca.figure_digest, ca.quotes, ca.framing, ca.articles AS read_articles"""
# fixed fragments, chosen by name: a client's words never reach the SQL
STORY_ORDER = {"outlets": "s.outlet_count DESC, s.article_count DESC, s.id",
               "latest": "s.latest DESC NULLS LAST, s.id",
               # scored in Python below; this only makes the input stable
               "differences": "s.id"}


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


def card(row):
    """One story in a list: what a story card on the site shows.

    comparable is the static site's rule for giving a story a page: two outlets
    could be read, and they share at least one fact. None until it is known.
    """
    analysed = row["sources_used"] is not None
    readability, _ = _readability(row["read_articles"])
    consensus = row["consensus"] or []
    comparable = None
    if analysed and readability["recorded"]:
        comparable = len(readability["readable_outlets"]) >= 2 and bool(consensus)
    return {
        "id": row["id"], "headline": row["title_summary"] or row["latest_title"],
        "topic": row["topic_label"], "outlets": row["outlets"],
        "article_count": row["article_count"], "coherence": row["coherence"],
        "latest": row["latest"], "status": _status(row), "analysed_at": row["analyzed_at"],
        "differences": differences(row) if analysed else None,
        "facts_not_in_every_outlet": gaps_in({"consensus": consensus}) if analysed else None,
        "numbers_to_compare": summarise(row["figure_digest"] or [])["shared"] if analysed
        else None,
        "unread_outlets": readability["unread_outlets"],
        "comparable": comparable,
    }


def by_differences(cards):
    """Most checkable differences first; stories not yet analysed come last."""
    return sorted(cards, key=lambda c: (
        -c["differences"]["score"] if c["differences"] else 1,
        -(c["facts_not_in_every_outlet"] or 0), -len(c["outlets"]), c["id"]))


def rank_contested(rows, limit):
    """The stories whose coverage reports a dispute, most contested first, each
    with what was counted (backend/analysis/contention.py). What the coverage
    reports, not a finding that the outlets disagree."""
    scored = []
    for row in rows:
        score, reasons = contention(row["titles"], row["topic_label"], row["quotes"])
        if score >= LISTED:
            scored.append((score, reasons, row))
    scored.sort(key=lambda t: (-t[0], -len(t[2]["outlets"]),
                               -(t[2]["latest"].timestamp() if t[2]["latest"] else 0)))
    return [{**card(row), "contention": {"score": round(score, 2), "reasons": reasons}}
            for score, reasons, row in scored[:limit]]


def person_summary(row):
    """One row of the people list: what the site's people table shows. Every mention
    is stored, so the query leaves those out and this reads only each outlet's totals."""
    outlets, totals = row["outlets"] or {}, row["totals"] or {}
    person = {"outlets": outlets}
    return {"id": row["id"], "name": row["name"], "articles": row["articles"],
            "outlets": len(outlets), "built_at": row["built_at"],
            "title": overall_title(person) or None, "tone": overall_tone(person),
            "never_named_by": sorted((o for o in totals if o not in outlets),
                                     key=lambda o: -totals[o])}


def figure_view(row):
    """What the Numbers tab shows for one stored figure.

    credited_to is read again from the figure's sentence with the corrected rule,
    so a story analysed before DEF-45 no longer credits a figure to the pronoun
    "who" as if to the World Health Organization. The stored value came from the
    same sentence (digest.build_digest), so this is what a fresh analysis gives.
    """
    sentence = row.get("sentence") or ""
    return {"figure": row.get("figure"), "value": row.get("value"), "unit": row.get("unit"),
            "source": row.get("source"), "credited_to": cited_authority(sentence),
            "cumulative": bool(row.get("cumulative")), "currency": row.get("currency"),
            "breakdown": row.get("breakdown") or [], "sentence": sentence,
            "context": row.get("context") or sentence, "url": row.get("url")}


def number_sections(digest, rank=True):
    """A story's figures as the static site lays them out (build_site.figures_block).

    groups: figures from two or more outlets that count the same thing.
    ungrouped: the same kind of figure from several outlets, too far apart to
    call one quantity. solo: the only figure of its kind. The last two cannot be
    compared, and the site says which is which rather than calling both
    "reported by one outlet".
    """
    groups = digest_groups(digest, rank=rank)
    paired = {id(row) for group in groups for row in group["values"]}
    unpaired = [r for r in digest if r.get("unit") and id(r) not in paired]
    with_peers = {r["unit"] for r in unpaired if r.get("peers")}
    return {
        "groups": [{"unit": g["unit"], "sources": g["sources"],
                    "values": [figure_view(r) for r in g["values"]]} for g in groups],
        "ungrouped": [figure_view(r) for r in unpaired if r["unit"] in with_peers],
        "solo": [figure_view(r) for r in unpaired if r["unit"] not in with_peers],
    }


def voice(summary, limit=4):
    """The verbs an outlet reports a person's words with, grouped by what each verb
    conveys, or, when it never quotes them, the verbs of what they do. The same
    choice as the static site (build_site.words_used), returned as data."""
    speaking = Counter(summary.get("speaking_verbs") or {})
    if not speaking:
        acting = Counter(summary.get("acting_verbs") or {})
        return {"speaking": [], "acting": [headline_tense(v) for v, _ in acting.most_common(3)]}
    groups = {}
    for verb, _ in speaking.most_common(limit):
        groups.setdefault(VERB_TONE.get(family_of(verb), "other"), []).append(headline_tense(verb))
    return {"speaking": [{"tone": tone, "verbs": verbs} for tone, verbs in groups.items()],
            "acting": []}


def readability_by_outlet(stored_lists):
    """{outlet: {"read": n, "unread": m}} over stored analyses: in how many stories
    each outlet's article could be opened, and in how many none could. Analyses
    stored without the flags are skipped rather than guessed (see _readability)."""
    counts = {}
    for stored in stored_lists:
        readability, _ = _readability(stored)
        if not readability["recorded"]:
            continue
        for outlet in readability["readable_outlets"]:
            counts.setdefault(outlet, {"read": 0, "unread": 0})["read"] += 1
        for outlet in readability["unread_outlets"]:
            counts.setdefault(outlet, {"read": 0, "unread": 0})["unread"] += 1
    return counts


def source_summary(name, counts, topics, stories, opened, total):
    """One outlet as the sources page shows it. counts is its article count and
    dates, or None if it has no articles yet; topics is [(topic, articles)], most
    first; total is the article count across every configured outlet."""
    articles = counts["articles"] if counts else 0
    return {"slug": slug(name), "name": name, "website": WEBSITES.get(name),
            "note": STATE_MEDIA.get(name), "articles": articles,
            "share": round(articles / total, 4) if total else 0.0,
            "first": counts["first"] if counts else None,
            "latest": counts["latest"] if counts else None,
            "stories": stories, "opened": opened,
            "topics": [{"topic": topic, "articles": n} for topic, n in topics]}


def api_db_config():
    """The API's own read-only account where one is set (backend/db/api_role.py),
    otherwise the pipeline's."""
    user = os.environ.get("NEWSEYE_API_DB_USER")
    if not user:
        return DB_CONFIG
    return {**DB_CONFIG, "user": user, "password": os.environ.get("NEWSEYE_API_DB_PASSWORD", "")}


class Store:
    def __init__(self, max_connections=8):
        self._pool = None
        self._lock = threading.Lock()
        self._max = max_connections

    def _get_pool(self):
        with self._lock:
            if self._pool is None:
                config = api_db_config()
                if config is DB_CONFIG:
                    log.warning("using the pipeline's database account; for anything but "
                                "local use, create the API's own (backend/db/api_role.py)")
                try:
                    self._pool = ThreadedConnectionPool(1, self._max, options=READ_ONLY,
                                                        **config)
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

    def stories(self, limit, offset, min_outlets, sort="outlets", topic=None, source=None):
        """(total, one page of stories), most outlets first unless sort says otherwise,
        only those in one topic or covered by one outlet when topic or source is given.

        Differences are counted from each stored analysis, so that order reads
        every story in the window before taking the page."""
        params = story_params(min_outlets=min_outlets, topic=topic, source=source,
                              limit=limit, offset=offset)
        page = "" if sort == "differences" else "LIMIT %(limit)s OFFSET %(offset)s"
        with self.cursor() as cur:
            cur.execute(f"SELECT count(*) AS n FROM ({STORY_SQL}) s", params)
            total = cur.fetchone()["n"]
            cur.execute(f"""
                SELECT s.*, {CARD_COLUMNS}
                FROM ({STORY_SQL}) s
                LEFT JOIN cluster_analysis ca ON ca.cluster_id = s.id
                ORDER BY {STORY_ORDER[sort]}
                {page}
            """, params)
            rows = cur.fetchall()
        cards = [card(r) for r in rows]
        if sort == "differences":
            cards = by_differences(cards)[offset:offset + limit]
        return total, cards

    def contested(self, limit, days):
        """The latest stories whose coverage reports a dispute. The days count back
        from the newest article stored, so a corpus whose feeds paused still has a
        "latest"; the static site's Contested page does the same."""
        params = story_params(days=days)
        with self.cursor() as cur:
            cur.execute("SELECT max(published_utc) AS until FROM articles")
            until = cur.fetchone()["until"]
            cur.execute(f"""
                SELECT s.*, {CARD_COLUMNS}
                FROM ({STORY_SQL}) s
                LEFT JOIN cluster_analysis ca ON ca.cluster_id = s.id
                WHERE s.latest >= (SELECT max(published_utc) FROM articles)
                                  - make_interval(days => %(days)s)
            """, params)
            rows = cur.fetchall()
        return {"days": days, "until": until, "items": rank_contested(rows, limit)}

    def topics(self):
        """How many published multi-outlet stories each topic has."""
        with self.cursor() as cur:
            cur.execute(f"""
                SELECT coalesce(s.topic_label, 'General') AS topic, count(*) AS stories
                FROM ({STORY_SQL}) s
                GROUP BY 1
                ORDER BY 2 DESC, 1
            """, story_params())
            return [dict(r) for r in cur.fetchall()]

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
            people = self._people_named(cur, [m["url"] for m in members])
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
                "numbers": number_sections(row["figure_digest"] or []),
            } if analysed else None,
            "people": people,
        }

    def _people_named(self, cur, urls):
        """The listed people the people batch found named in these articles, as the
        parse decided, so a story set in Uhuru Park does not link to Uhuru Kenyatta.
        Empty until the people pages are built."""
        cur.execute("SELECT to_regclass('people') IS NOT NULL AS ok")
        if not urls or not cur.fetchone()["ok"]:
            return []
        cur.execute("""
            SELECT p.id, p.name
            FROM people p
            WHERE EXISTS (SELECT 1
                          FROM jsonb_each(p.outlets) AS o,
                               jsonb_array_elements(o.value -> 'records') AS r
                          WHERE r ->> 'url' = ANY(%s))
            ORDER BY p.name
        """, (list(urls),))
        return [dict(r) for r in cur.fetchall()]

    def search(self, query, limit):
        """Articles closest in meaning to the query, each with its story if it has one.

        A story too loose to compare has no page (NotPublished), so its articles
        stand alone rather than linking to a 404; the static site's search does the
        same."""
        # imported here: loading MiniLM takes seconds, and only search needs it
        from backend.nlp.search import embed_query
        vector = embed_query(query)
        with self.cursor() as cur:
            cur.execute("""
                SELECT a.id, a.title, a.source_name, a.url, a.published_utc, a.snippet,
                       c.id AS cluster_id, 1 - (a.embedding <=> %(v)s::vector) AS similarity
                FROM articles a
                LEFT JOIN cluster_members cm ON cm.article_id = a.id
                LEFT JOIN clusters c ON c.id = cm.cluster_id AND c.coherence >= %(floor)s
                WHERE a.embedding IS NOT NULL
                ORDER BY a.embedding <=> %(v)s::vector
                LIMIT %(limit)s
            """, {"v": vector, "limit": limit, "floor": CLUSTER_MIN_COHERENCE})
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
                SELECT id, name, articles, built_at, totals,
                       (SELECT jsonb_object_agg(o.key, o.value - 'records')
                        FROM jsonb_each(outlets) AS o) AS outlets
                FROM people ORDER BY articles DESC, name
            """)
            rows = cur.fetchall()
        if not rows:
            raise NotBuilt("People pages have not been built: run python -m backend.people")
        return [person_summary(r) for r in rows]

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
                                      "records": summary.get("records", [])[:records],
                                      "voice": voice(summary)}
                             for outlet, summary in person["outlets"].items()}
        return person

    # ------------------------------------------------------------------ sources
    def _sources(self):
        """Every configured outlet with its counts and its full topic mix."""
        names = list(SOURCES.values())
        with self.cursor() as cur:
            cur.execute("""
                SELECT source_name AS name, count(*) AS articles,
                       min(published_utc) AS first, max(published_utc) AS latest
                FROM articles
                WHERE source_name = ANY(%(names)s)
                GROUP BY source_name
            """, {"names": names})
            counts = {r["name"]: r for r in cur.fetchall()}
            cur.execute("""
                SELECT source_name AS name, coalesce(category, %(fallback)s) AS topic,
                       count(*) AS n
                FROM articles
                WHERE source_name = ANY(%(names)s)
                GROUP BY 1, 2
            """, {"names": names, "fallback": FALLBACK_LABEL})
            topics = {}
            for r in cur.fetchall():
                topics.setdefault(r["name"], []).append((r["topic"], r["n"]))
            cur.execute(f"""
                SELECT o.name, count(*) AS n
                FROM ({STORY_SQL}) s
                CROSS JOIN LATERAL unnest(s.outlets) AS o(name)
                GROUP BY o.name
            """, story_params())
            stories = {r["name"]: r["n"] for r in cur.fetchall()}
            cur.execute("""
                SELECT ca.articles
                FROM cluster_analysis ca
                JOIN clusters c ON c.id = ca.cluster_id
                WHERE ca.sources_used IS NOT NULL AND c.coherence >= %(floor)s
            """, {"floor": CLUSTER_MIN_COHERENCE})
            opened = readability_by_outlet(r["articles"] for r in cur.fetchall())
        total = sum(r["articles"] for r in counts.values())
        found = [source_summary(name, counts.get(name),
                                sorted(topics.get(name, []), key=lambda t: (-t[1], t[0])),
                                stories.get(name, 0), opened.get(name), total)
                 for name in names]
        return sorted(found, key=lambda s: (-s["articles"], s["name"]))

    def sources(self):
        """Every outlet Newseye reads, most articles first, each with its leading
        topics. "General" is the label for no clear topic, so it is not one of them."""
        return [{**s, "topics": [t for t in s["topics"]
                                 if t["topic"] != FALLBACK_LABEL][:SOURCE_TOPICS_LISTED]}
                for s in self._sources()]

    def source(self, name, stories=10, recent=12):
        """One outlet: its counts, its whole topic mix, its newest headlines (each
        with its story if it is in one with a page) and its newest stories."""
        summary = next((s for s in self._sources() if s["name"] == name), None)
        if summary is None:
            return None
        with self.cursor() as cur:
            cur.execute(f"""
                WITH published AS ({STORY_SQL})
                SELECT a.id, a.title, a.url, a.published_utc, a.snippet,
                       max(p.id) AS story_id
                FROM articles a
                LEFT JOIN cluster_members cm ON cm.article_id = a.id
                LEFT JOIN published p ON p.id = cm.cluster_id
                WHERE a.source_name = %(outlet)s
                GROUP BY a.id
                ORDER BY a.published_utc DESC NULLS LAST, a.id DESC
                LIMIT %(recent)s
            """, story_params(outlet=name, recent=recent))
            headlines = cur.fetchall()
        _, cards = self.stories(stories, 0, 2, "latest", source=name)
        return {**summary,
                "recent": [{"id": r["id"], "title": r["title"], "url": r["url"],
                            "published": r["published_utc"], "snippet": clean(r["snippet"]),
                            "story_id": r["story_id"]} for r in headlines],
                "stories_covered": cards}
