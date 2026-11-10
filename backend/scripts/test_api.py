"""Does the web API answer correctly, refuse bad input and fail safely?

Black-box tests through FastAPI's test client against a fake data layer, so no
database is needed: routes, input validation, error codes, what an error reveals,
CORS and the read-only guarantees. --live adds checks against the real
database, including that a write through the API's connection is refused.

    python -m backend.scripts.test_api
    python -m backend.scripts.test_api --live
"""
import logging
import os
import secrets
import sys
from datetime import UTC, datetime
from unittest import mock

import psycopg2
from fastapi.testclient import TestClient

from backend.analysis.contention import disputed
from backend.analysis.digest import build_digest
from backend.api import store as store_module
from backend.api.main import CONTENT_POLICY, RateLimiter, app, get_limiter, get_store
from backend.api.store import (
    READ_ONLY,
    SOURCES,
    DatabaseUnavailable,
    NotBuilt,
    NotPublished,
    api_db_config,
    by_differences,
    card,
    clean,
    figure_view,
    number_sections,
    person_summary,
    rank_contested,
    readability_by_outlet,
    slug,
    voice,
)
from backend.config import CLUSTER_MIN_COHERENCE, RSS_FEEDS
from backend.db import api_role
from backend.db.connection import DB_CONFIG
from backend.scripts.testkit import case, report

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
DIFF = {"score": 2, "reasons": ["outlets worded 1 fact differently",
                                "1 quote shortened or reworded"]}
SUMMARY = {"id": 903, "headline": "Ruto accuses Kenyatta of betrayal", "topic": "Politics",
           "outlets": ["Capital FM", "KBC", "Nairobi Wire"], "article_count": 7,
           "coherence": 0.71, "latest": NOW, "status": "analysed", "analysed_at": NOW,
           "differences": DIFF, "facts_not_in_every_outlet": 3, "numbers_to_compare": 1,
           "unread_outlets": ["Nation Africa"], "comparable": True}
STORY = {**SUMMARY, "subject": "Kenyatta", "clustered_at": NOW,
         "readability": {"recorded": True, "readable_outlets": ["Capital FM", "KBC"],
                         "unread_outlets": ["Nation Africa"]},
         "articles": [{"id": 1, "outlet": "KBC", "title": "Ruto accuses Uhuru",
                       "url": "https://www.kbc.co.ke/a", "published": NOW,
                       "snippet": "President William Ruto has described", "readable": True},
                      {"id": 2, "outlet": "Nation Africa", "title": "Ruto calls Uhuru a fraudster",
                       "url": "https://nation.africa/b", "published": NOW, "snippet": None,
                       "readable": False}],
         "analysis": {"coverage": [], "quotes": [], "figures": [], "framing": [],
                      "differences": DIFF,
                      "numbers": {"groups": [{"unit": "people", "sources": ["KBC", "Capital FM"],
                                              "values": []}], "ungrouped": [], "solo": []}},
         "people": [{"id": "william-ruto", "name": "William Ruto"}]}
PERSON = {"id": "william-ruto", "name": "William Ruto", "aliases": ["Ruto"], "articles": 567,
          "outlets": {"KBC": {"articles": 39}}, "totals": {"KBC": 464},
          "period_first": NOW, "period_last": NOW, "built_at": NOW}
SOURCE = {"slug": "capital-fm", "name": "Capital FM", "website": "https://www.capitalfm.co.ke",
          "note": None, "articles": 812, "share": 0.0998, "first": NOW, "latest": NOW,
          "stories": 31, "opened": {"read": 24, "unread": 2},
          "topics": [{"topic": "Politics", "articles": 120}]}


class FakeStore:
    """Answers like Store; `fail` makes every read raise that exception."""

    def __init__(self, fail=None, people_built=True):
        self.fail, self.people_built, self.calls = fail, people_built, []

    def _check(self, name):
        self.calls.append(name)
        if self.fail:
            raise self.fail

    def health(self):
        self._check("health")
        return {"articles": 7551, "stories": 261, "analysed": 40, "people": 50,
                "last_article": NOW, "last_clustered": NOW}

    def stories(self, limit, offset, min_outlets, sort="outlets", topic=None, source=None):
        self._check("stories")
        self.sort, self.topic, self.source = sort, topic, source
        return 1, [SUMMARY][:limit]

    def sources(self):
        self._check("sources")
        return [SOURCE]

    def source(self, name, stories=10, recent=12):
        self._check("source")
        if name != "Capital FM":
            return None
        return {**SOURCE, "recent": [{"id": 4, "title": "Ruto accuses Uhuru",
                                      "url": "https://www.capitalfm.co.ke/d", "published": NOW,
                                      "snippet": "x", "story_id": 903}],
                "stories_covered": [SUMMARY][:stories]}

    def contested(self, limit, days):
        self._check("contested")
        return {"days": days, "until": NOW, "items": [
            {**SUMMARY, "contention": {"score": 1.25,
                                       "reasons": ["2 of 2 headlines report a dispute",
                                                   "Politics"]}}][:limit]}

    def topics(self):
        self._check("topics")
        return [{"topic": "Politics", "stories": 3}, {"topic": "General", "stories": 2}]

    def story(self, story_id):
        self._check("story")
        if story_id == 13:
            raise NotPublished(story_id)
        return STORY if story_id == 903 else None

    def search(self, query, limit):
        self._check("search")
        return [{"id": 1, "title": "Housing levy row", "outlet": "KBC",
                 "url": "https://www.kbc.co.ke/c", "published": NOW, "snippet": "x",
                 "story_id": 903, "similarity": 0.61}]

    def people(self):
        self._check("people")
        if not self.people_built:
            raise NotBuilt("People pages have not been built: run python -m backend.people")
        return [{"id": "william-ruto", "name": "William Ruto", "articles": 567,
                 "outlets": 10, "built_at": NOW, "title": "President",
                 "tone": {"n": 10, "negative": 0.2, "positive": 0.3},
                 "never_named_by": ["The Sharp Daily"]}]

    def person(self, person_id, records=20):
        self._check("person")
        return PERSON if person_id == "william-ruto" else None


def client(fake, limiter=None):
    app.dependency_overrides[get_store] = lambda: fake
    limiter = limiter or RateLimiter(100_000, 100_000)
    app.dependency_overrides[get_limiter] = lambda: limiter
    return TestClient(app, raise_server_exceptions=False)


def stored(id=1, score_facts=0, read=("KBC", "Capital FM"), unread=(), analysed=True,
           titles=("Budget passed",), topic=None):
    """A database row as the story queries return it."""
    consensus = [{"anchor": {"text": "x"}, "reported_by": ["KBC"], "omitted_by": ["Capital FM"]}
                 for _ in range(score_facts)]
    articles = ([{"source": o, "url": o, "fetched": True} for o in read]
                + [{"source": o, "url": o, "fetched": False} for o in unread])
    return {"id": id, "title_summary": "Headline", "latest_title": "Latest", "topic_label": topic,
            "outlets": sorted(set(read) | set(unread)), "article_count": 2, "coherence": 0.7,
            "latest": NOW, "sources_used": len(read) if analysed else None, "analyzed_at": NOW,
            "consensus": consensus if analysed else None, "figure_digest": [], "quotes": [],
            "framing": [], "read_articles": articles if analysed else None, "titles": list(titles)}


def get(fake, path, **kwargs):
    return client(fake).get(path, **kwargs)


def results():
    rows = []

    def check(name, expected, actual, ok, trace):
        rows.append(case(name, expected, actual, ok, trace=trace))

    # ------------------------------------------------------------- happy paths
    r = get(FakeStore(), "/api/health")
    check("health reports the database's counts", "200, status ok, 7551 articles",
          f"{r.status_code}, status {r.json().get('status')}, {r.json().get('articles')} articles",
          r.status_code == 200 and r.json()["articles"] == 7551, "NFR-02")

    r = get(FakeStore(), "/api/stories?limit=5")
    body = r.json()
    check("story list: one page, dashboard order, with checkable differences",
          "200, total 1, first id 903, score 2",
          f"{r.status_code}, total {body.get('total')}, first id "
          f"{body['items'][0]['id'] if body.get('items') else '-'}, score "
          f"{body['items'][0]['differences']['score'] if body.get('items') else '-'}",
          r.status_code == 200 and body["total"] == 1 and body["items"][0]["id"] == 903
          and body["items"][0]["differences"]["score"] == 2, "FR-08")

    fake = FakeStore()
    r = get(fake, "/api/stories?sort=differences")
    check("story list can be ordered by differences", "200, passed through as 'differences'",
          f"{r.status_code}, passed through as {getattr(fake, 'sort', None)!r}",
          r.status_code == 200 and fake.sort == "differences", "FR-08")

    r = get(FakeStore(), "/api/stories")
    item = r.json()["items"][0]
    check("a story card carries what the site's card shows",
          "3 facts not in every outlet, 1 number, Nation Africa unread, comparable",
          f"{item.get('facts_not_in_every_outlet')} facts not in every outlet, "
          f"{item.get('numbers_to_compare')} number, {item.get('unread_outlets')} unread, "
          f"comparable {item.get('comparable')}",
          item.get("facts_not_in_every_outlet") == 3 and item.get("numbers_to_compare") == 1
          and item.get("unread_outlets") == ["Nation Africa"] and item.get("comparable") is True,
          "FR-08, NFR-04")

    r = get(FakeStore(), "/api/contested?days=7")
    body = r.json()
    check("contested stories say what was counted", "200, 7 days, reasons on the story",
          f"{r.status_code}, {body.get('days')} days, "
          f"{body['items'][0]['contention']['reasons'] if body.get('items') else '-'}",
          r.status_code == 200 and body["days"] == 7
          and body["items"][0]["contention"]["reasons"], "FR-08, NFR-04")

    r = get(FakeStore(), "/api/topics")
    check("topics list the story counts", "200, Politics 3",
          f"{r.status_code}, {r.json()[0] if r.status_code == 200 else '-'}",
          r.status_code == 200 and r.json()[0] == {"topic": "Politics", "stories": 3}, "FR-08")

    # ---------------------------------- the rules behind the cards and lists
    unread = card(stored(read=("KBC", "Capital FM"), unread=("People Daily",), score_facts=2))
    check("a card names the unread outlet and counts facts only among the readable",
          "People Daily unread, 2 facts, comparable",
          f"{unread['unread_outlets']} unread, {unread['facts_not_in_every_outlet']} facts, "
          f"comparable {unread['comparable']}",
          unread["unread_outlets"] == ["People Daily"]
          and unread["facts_not_in_every_outlet"] == 2 and unread["comparable"] is True, "NFR-04")

    one = card(stored(read=("KBC",), unread=("People Daily",), score_facts=1))
    check("one readable outlet: nothing to compare, as on the site", "comparable False",
          f"comparable {one['comparable']}", one["comparable"] is False, "NFR-04")

    waiting = card(stored(analysed=False))
    check("a story not analysed yet claims nothing", "no counts, comparable unknown",
          f"facts {waiting['facts_not_in_every_outlet']}, comparable {waiting['comparable']}, "
          f"unread {waiting['unread_outlets']}",
          waiting["facts_not_in_every_outlet"] is None and waiting["comparable"] is None
          and waiting["unread_outlets"] is None and waiting["differences"] is None, "NFR-04")

    order = by_differences([
        {"id": 1, "differences": None, "facts_not_in_every_outlet": None, "outlets": ["a"] * 9},
        {"id": 2, "differences": {"score": 0}, "facts_not_in_every_outlet": 0, "outlets": ["a"]},
        {"id": 3, "differences": {"score": 4}, "facts_not_in_every_outlet": 1, "outlets": ["a"]},
        {"id": 4, "differences": {"score": 4}, "facts_not_in_every_outlet": 2, "outlets": ["a"]},
    ])
    check("most differences first, unanalysed last", "4, 3, 2, 1",
          ", ".join(str(c["id"]) for c in order),
          [c["id"] for c in order] == [4, 3, 2, 1], "FR-08")

    ranked = rank_contested([
        stored(id=1, titles=("Budget passed", "Budget passed", "Row over budget", "Budget")),
        stored(id=2, titles=("Ruto accuses Gachagua", "Gachagua denies claims")),
        stored(id=3, titles=("Probe into arrest of journalist", "Weather today"),
               topic="Security"),
    ], 10)
    check("contested: half the headlines or a security story; one in four is not listed",
          "2 then 3, 1 left out", ", ".join(str(c["id"]) for c in ranked),
          [c["id"] for c in ranked] == [2, 3], "FR-08")
    forms = ["Gachagua denies claims", "Ruto denied the report", "Bishops decry killings",
             "MPs accusing CS", "Blaming the governor", "Uhuru hits back at Ruto"]
    plain_news = ["Milk output hits 5.2B litres", "Kenya beats Uganda 2-0"]
    check("contested: a dispute verb counts in every form, and bare 'hits' does not",
          f"{len(forms)} of {len(forms)}; 0 of {len(plain_news)}",
          f"{disputed(forms)} of {len(forms)}; {disputed(plain_news)} of {len(plain_news)}",
          disputed(forms) == len(forms) and disputed(plain_news) == 0, "FR-08")
    check("contested: the reasons say what was counted", "2 of 2 headlines report a dispute",
          "; ".join(ranked[0]["contention"]["reasons"]),
          "2 of 2 headlines report a dispute" in ranked[0]["contention"]["reasons"], "NFR-04")

    r = get(FakeStore(), "/api/stories/903")
    body = r.json()
    check("story page names the outlet that could not be opened",
          "200, unread Nation Africa, its article readable false",
          f"{r.status_code}, unread {body['readability']['unread_outlets']}, readable "
          f"{[a['readable'] for a in body['articles']]}" if r.status_code == 200
          else str(r.status_code),
          r.status_code == 200 and body["readability"]["unread_outlets"] == ["Nation Africa"]
          and body["articles"][1]["readable"] is False, "NFR-04")

    r = get(FakeStore(), "/api/search?q=%20housing%20%20levy%20")
    check("search tidies the query and returns hits with their story",
          "200, query 'housing levy', story 903",
          f"{r.status_code}, query {r.json().get('query')!r}, story "
          f"{r.json()['results'][0]['story_id'] if r.status_code == 200 else '-'}",
          r.status_code == 200 and r.json()["query"] == "housing levy"
          and r.json()["results"][0]["story_id"] == 903, "FR-10")

    r = get(FakeStore(), "/api/people")
    row = r.json()[0] if r.status_code == 200 else {}
    check("people list carries what the site's table shows",
          "200, President, tone over 10 lines, never named by The Sharp Daily",
          f"{r.status_code}, {row.get('title')}, tone over {(row.get('tone') or {}).get('n')} "
          f"lines, never named by {row.get('never_named_by')}",
          row.get("title") == "President" and row.get("tone", {}).get("n") == 10
          and row.get("never_named_by") == ["The Sharp Daily"], "FR-07")

    summary = person_summary({
        "id": "x", "name": "X", "articles": 30, "built_at": NOW,
        "totals": {"KBC": 100, "Capital FM": 50, "K24 Digital": 200, "The East African": 80},
        "outlets": {"KBC": {"titles": {"president": 3, "(no title)": 9},
                            "title_forms": {"president": "President"},
                            "tone": {"n": 10, "negative": 0.5, "positive": 0.0}},
                    "Capital FM": {"titles": {"(no title)": 2}, "title_forms": {},
                                   "tone": {"n": 30, "negative": 0.1, "positive": 0.4}}}})
    check("a person's tone is weighted by headlines, and absent outlets are named, largest first",
          "negative 0.2, positive 0.3; President; K24 Digital, The East African",
          f"negative {summary['tone']['negative']:.1f}, positive {summary['tone']['positive']:.1f}; "
          f"{summary['title']}; {', '.join(summary['never_named_by'])}",
          round(summary["tone"]["negative"], 3) == 0.2 and round(summary["tone"]["positive"], 3) == 0.3
          and summary["title"] == "President"
          and summary["never_named_by"] == ["K24 Digital", "The East African"], "FR-07")

    r = get(FakeStore(), "/api/people/william-ruto")
    check("person page", "200, William Ruto, 567 articles",
          f"{r.status_code}, {r.json().get('name')}, {r.json().get('articles')} articles",
          r.status_code == 200 and r.json()["articles"] == 567, "FR-07")

    # --------------------------------------------------------- refused input
    for path, why in [("/api/stories?limit=0", "limit below 1"),
                      ("/api/stories?limit=101", "limit above 100"),
                      ("/api/stories?offset=-1", "negative offset"),
                      ("/api/stories?sort=id;DROP%20TABLE%20articles", "unknown sort order"),
                      ("/api/contested?days=0", "contested window of no days"),
                      ("/api/contested?days=91", "contested window too long"),
                      ("/api/stories/abc", "story id not a number"),
                      ("/api/stories/0", "story id below 1"),
                      ("/api/search?q=a", "query of one character"),
                      ("/api/search?q=" + "x" * 201, "query over 200 characters"),
                      ("/api/search?q=%20%20%20", "query of spaces only"),
                      ("/api/people/Robert';DROP%20TABLE%20people;--", "person id with SQL")]:
        fake = FakeStore()
        r = get(fake, path)
        reached = [c for c in fake.calls
                   if c in ("story", "search", "person", "stories", "contested")]
        check(f"refused before the database: {why}", "422, data layer not called",
              f"{r.status_code}, data layer {'called' if reached else 'not called'}",
              r.status_code == 422 and not reached, "NFR-03")

    # ---------------------------------------------------------- not found
    for path, why in [("/api/stories/999", "no such story"),
                      ("/api/stories/13", "story too loose to compare"),
                      ("/api/people/nobody", "no such person")]:
        r = get(FakeStore(), path)
        check(f"404: {why}", "404 with a reason", f"{r.status_code}: {r.json().get('detail')}",
              r.status_code == 404 and bool(r.json().get("detail")), "FR-09")

    # ------------------------------------------------------- failing safely
    secret = "password=hunter2 host=10.0.0.5"
    r = get(FakeStore(fail=DatabaseUnavailable(secret)), "/api/stories")
    check("database down: 503, and nothing about the connection", "503 Database unavailable",
          f"{r.status_code} {r.json().get('detail')}",
          r.status_code == 503 and r.json() == {"detail": "Database unavailable"}
          and secret not in r.text, "NFR-02")

    r = get(FakeStore(fail=RuntimeError(secret)), "/api/stories/903")
    check("unexpected error: 500 with no exception text", "500 Internal error",
          f"{r.status_code} {r.json().get('detail')}",
          r.status_code == 500 and r.json() == {"detail": "Internal error"}
          and secret not in r.text and "Traceback" not in r.text, "NFR-03")

    r = get(FakeStore(people_built=False), "/api/people")
    check("people not built yet: 503 that says how to build them", "503 naming backend.people",
          f"{r.status_code} {r.json().get('detail')}",
          r.status_code == 503 and "backend.people" in r.json()["detail"], "NFR-02")

    # ------------------------------------------------------- read only, safe
    r = client(FakeStore()).post("/api/stories", json={})
    check("writing is not possible: POST is refused", "405",
          str(r.status_code), r.status_code == 405, "NFR-03")

    r = client(FakeStore()).options("/api/stories", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    allowed = r.headers.get("access-control-allow-origin")
    r2 = client(FakeStore()).options("/api/stories", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    check("CORS: the React dev server is allowed, other sites are not",
          "allowed http://localhost:5173; none for evil.example",
          f"allowed {allowed}; {r2.headers.get('access-control-allow-origin') or 'none'} "
          f"for evil.example",
          allowed == "http://localhost:5173"
          and r2.headers.get("access-control-allow-origin") is None, "NFR-03")

    r = get(FakeStore(), "/api/health")
    check("every response forbids content sniffing", "X-Content-Type-Options nosniff",
          f"X-Content-Type-Options {r.headers.get('x-content-type-options')}",
          r.headers.get("x-content-type-options") == "nosniff", "NFR-03")

    check("every API response forbids loading or framing anything",
          CONTENT_POLICY, r.headers.get("content-security-policy"),
          r.headers.get("content-security-policy") == CONTENT_POLICY, "NFR-03")

    # ------------------------------------------------------------ rate limits
    now = [0.0]
    limiter = RateLimiter(2, 1, clock=lambda: now[0])
    answers = [limiter.wait("a", "all"), limiter.wait("a", "all"), limiter.wait("a", "all"),
               limiter.wait("b", "all")]
    check("the limit is per client", "third request from a waits; b is unaffected",
          f"waits {answers}", answers[:2] == [0, 0] and answers[2] > 0 and answers[3] == 0,
          "NFR-03")
    now[0] = 61.0
    check("the limit lifts after a minute", "0", str(limiter.wait("a", "all")),
          limiter.wait("a", "all") == 0, "NFR-03")

    api = client(FakeStore(), RateLimiter(2, 100))
    seen = [api.get("/api/health") for _ in range(3)]
    check("too many requests: 429 with when to retry", "200, 200, 429 and Retry-After",
          f"{[x.status_code for x in seen]}, Retry-After {seen[2].headers.get('retry-after')}",
          [x.status_code for x in seen] == [200, 200, 429]
          and int(seen[2].headers.get("retry-after", 0)) > 0, "NFR-03")

    fake = FakeStore()
    api = client(fake, RateLimiter(100, 1))
    seen = [api.get("/api/search?q=housing") for _ in range(2)] + [api.get("/api/health")]
    check("search has its own lower limit; other routes still answer", "200, 429, then 200",
          f"{[x.status_code for x in seen]}, model calls {fake.calls.count('search')}",
          [x.status_code for x in seen] == [200, 429, 200] and fake.calls.count("search") == 1,
          "NFR-03")

    api = client(FakeStore(), RateLimiter(1, 100))
    api.get("/api/health")
    r = api.get("/api/health", headers={"Origin": "http://localhost:5173"})
    check("a browser can read the 429: CORS headers are on it",
          "429, allowed http://localhost:5173",
          f"{r.status_code}, allowed {r.headers.get('access-control-allow-origin')}",
          r.status_code == 429
          and r.headers.get("access-control-allow-origin") == "http://localhost:5173", "NFR-03")

    # ------------------------------------------------------ the database account
    with mock.patch.dict(os.environ, {"NEWSEYE_API_DB_USER": "newseye_api",
                                      "NEWSEYE_API_DB_PASSWORD": "x" * 12}):
        own = api_db_config()
    with mock.patch.dict(os.environ):
        os.environ.pop("NEWSEYE_API_DB_USER", None)
        shared = api_db_config()
    check("the API logs in with its own account when one is set",
          "newseye_api when set, otherwise the pipeline's",
          f"{own['user']} when set, otherwise {shared['user']}",
          own["user"] == "newseye_api" and shared is DB_CONFIG, "NFR-03")

    check("database sessions are read-only, with a statement timeout",
          "default_transaction_read_only=on and statement_timeout",
          READ_ONLY, "default_transaction_read_only=on" in READ_ONLY
          and "statement_timeout" in READ_ONLY, "NFR-03")

    raw = '<p><a href="https://thekenyatimes.com" rel="nofollow">The Kenya Times</a> Ruto &amp; Raila'
    check("snippets reach the client as plain text (DEF-39)", "The Kenya Times Ruto & Raila",
          clean(raw), clean(raw) == "The Kenya Times Ruto & Raila", "NFR-03")

    # --------------------------------- sources and filters (added for the React site);
    # last, so the case ids cited elsewhere stay as they are
    r = get(FakeStore(), "/api/sources")
    first = r.json()[0] if r.status_code == 200 else {}
    check("sources list each outlet's counts and leading topics, not a rating",
          "200, capital-fm, 812 articles, 31 stories, opened 24 of 26, Politics",
          f"{r.status_code}, {first.get('slug')}, {first.get('articles')} articles, "
          f"{first.get('stories')} stories, opened {(first.get('opened') or {}).get('read')} of "
          f"{sum((first.get('opened') or {}).values())}, "
          f"{', '.join(t['topic'] for t in first.get('topics', []))}",
          r.status_code == 200 and first.get("slug") == "capital-fm"
          and first.get("opened") == {"read": 24, "unread": 2}
          and "rating" not in r.text and "score" not in r.text, "FR-09, NFR-04")

    r = get(FakeStore(), "/api/sources/capital-fm")
    body = r.json() if r.status_code == 200 else {}
    check("a source page lists its newest headlines with their stories, and its stories",
          "200, headline linked to story 903, 1 story",
          f"{r.status_code}, headline linked to story "
          f"{body['recent'][0]['story_id'] if body.get('recent') else '-'}, "
          f"{len(body.get('stories_covered', []))} story",
          r.status_code == 200 and body["recent"][0]["story_id"] == 903
          and len(body["stories_covered"]) == 1, "FR-09")

    fake = FakeStore()
    r = get(fake, "/api/sources/the-daily-planet")
    check("404: no such source, and the data layer is not asked", "404 with a reason, not called",
          f"{r.status_code}: {r.json().get('detail')}, "
          f"{'called' if 'source' in fake.calls else 'not called'}",
          r.status_code == 404 and r.json().get("detail") and "source" not in fake.calls, "FR-09")

    fake = FakeStore()
    r = get(fake, "/api/sources/capital';DROP%20TABLE%20articles;--")
    check("refused before the database: source name with SQL", "422, data layer not called",
          f"{r.status_code}, data layer {'called' if fake.calls else 'not called'}",
          r.status_code == 422 and not fake.calls, "NFR-03")

    fake = FakeStore()
    r = get(fake, "/api/stories?source=capital-fm")
    check("stories one outlet covered: its slug reaches the data layer as its name",
          "200, filtered by 'Capital FM'",
          f"{r.status_code}, filtered by {getattr(fake, 'source', None)!r}",
          r.status_code == 200 and fake.source == "Capital FM", "FR-09")

    for path, why in [("/api/stories?source=the-daily-planet", "an outlet Newseye does not read"),
                      ("/api/stories?topic=Politics'%20OR%201=1", "a topic that is not one"),
                      ("/api/stories?source=CAPITAL", "an outlet name that is not a slug")]:
        fake = FakeStore()
        r = get(fake, path)
        check(f"refused before the database: {why}", "422, data layer not called",
              f"{r.status_code}, data layer {'called' if fake.calls else 'not called'}",
              r.status_code == 422 and not fake.calls, "NFR-03")

    fake = FakeStore()
    r = get(fake, "/api/stories?topic=Politics&sort=latest")
    check("stories in one topic: the topic and the order reach the data layer",
          "200, Politics, latest", f"{r.status_code}, {getattr(fake, 'topic', None)}, "
          f"{getattr(fake, 'sort', None)}",
          r.status_code == 200 and fake.topic == "Politics" and fake.sort == "latest", "FR-09")

    slugs = {slug(feed["name"]) for feed in RSS_FEEDS}
    check("every outlet has its own link name", f"the-kenya-times; {len(RSS_FEEDS)} distinct",
          f"{slug('The Kenya Times')}; {len(slugs)} distinct",
          slug("The Kenya Times") == "the-kenya-times" and len(slugs) == len(RSS_FEEDS)
          and set(SOURCES) == slugs, "FR-09")

    opened = readability_by_outlet([
        [{"source": "KBC", "url": "a", "fetched": True},
         {"source": "People Daily", "url": "b", "fetched": False}],
        [{"source": "KBC", "url": "c", "fetched": False},
         {"source": "KBC", "url": "d", "fetched": True}],
        None])
    check("how often an outlet could be opened: per story, unrecorded analyses skipped",
          "KBC read 2 unread 0; People Daily read 0 unread 1",
          f"KBC read {opened['KBC']['read']} unread {opened['KBC']['unread']}; People Daily "
          f"read {opened['People Daily']['read']} unread {opened['People Daily']['unread']}",
          opened == {"KBC": {"read": 2, "unread": 0},
                     "People Daily": {"read": 0, "unread": 1}}, "NFR-04")

    digest = build_digest([
        {"text": "The death toll rose to 47 on Tuesday", "source": "Nation", "article_id": 1},
        {"text": "Officials confirmed 52 dead in the incident", "source": "KBC", "article_id": 2},
        {"text": "The ministry spent $5 million on the anti-doping programme",
         "source": "Nation", "article_id": 3},
        {"text": "Sponsors pledged $2 billion to the federation", "source": "KBC",
         "article_id": 4},
        {"text": "Traders were given 90 days to comply", "source": "Capital FM",
         "article_id": 5}])
    laid = number_sections(digest, rank=False)
    check("a story's numbers: comparable groups, then the same kind too far apart, then "
          "the only one of its kind", "1 group (47, 52); 2 ungrouped; 1 solo (90)",
          f"{len(laid['groups'])} group "
          f"({', '.join(v['figure'] for g in laid['groups'] for v in g['values'])}); "
          f"{len(laid['ungrouped'])} ungrouped; {len(laid['solo'])} solo "
          f"({', '.join(v['figure'] for v in laid['solo'])})",
          [sorted(v["figure"] for v in g["values"]) for g in laid["groups"]] == [["47", "52"]]
          and len(laid["ungrouped"]) == 2 and [v["figure"] for v in laid["solo"]] == ["90"],
          "FR-06")

    old = figure_view({"figure": "3.5 million", "credited_to": "who", "source": "Capital FM",
                       "sentence": '"Now, salaried people, the 3.5 million Kenyans who are in '
                                   'formal employment," Mbadi said.'})
    agency = figure_view({"figure": "3 million", "credited_to": "WHO", "source": "KBC",
                          "sentence": "According to WHO, 3 million doses were delivered."})
    check("a figure stored before DEF-45 is no longer credited to the pronoun \"who\"",
          "None for the pronoun; WHO for the agency",
          f"{old['credited_to']} for the pronoun; {agency['credited_to']} for the agency",
          old["credited_to"] is None and agency["credited_to"] == "WHO", "FR-06")

    words = voice({"speaking_verbs": {"say": 5, "praise": 2, "accuse": 1},
                   "acting_verbs": {"meet": 3}})
    acts = voice({"speaking_verbs": {}, "acting_verbs": {"meet": 3, "tour": 1}})
    check("a person's verbs are grouped by what they convey; actions when never quoted",
          "neutral: says; praising: praises; critical: accuses | meets, tours",
          "; ".join(f"{g['tone']}: {', '.join(g['verbs'])}" for g in words["speaking"])
          + " | " + ", ".join(acts["acting"]),
          [(g["tone"], g["verbs"]) for g in words["speaking"]]
          == [("neutral", ["says"]), ("praising", ["praises"]), ("critical", ["accuses"])]
          and acts == {"speaking": [], "acting": ["meets", "tours"]}, "FR-07")

    r = get(FakeStore(), "/api/stories/903")
    body = r.json() if r.status_code == 200 else {}
    check("a story page carries its number groups and the people named in it",
          "200, 1 number group, William Ruto",
          f"{r.status_code}, {len((body.get('analysis') or {}).get('numbers', {}).get('groups', []))}"
          f" number group, {', '.join(p['name'] for p in body.get('people', []))}",
          r.status_code == 200 and len(body["analysis"]["numbers"]["groups"]) == 1
          and body["people"] == [{"id": "william-ruto", "name": "William Ruto"}], "FR-06, FR-07")

    app.dependency_overrides.clear()
    return rows


def live_results():
    """Against the real database: requires DB_PASSWORD and a migrated schema."""
    rows = []
    real = store_module.Store(max_connections=2)
    app.dependency_overrides.clear()
    api = TestClient(app, raise_server_exceptions=False)
    r = api.get("/api/health")
    rows.append(case("live: health", "200", f"{r.status_code} {r.json()}",
                     r.status_code == 200, trace="NFR-02"))
    r = api.get("/api/stories?limit=3")
    first = r.json()["items"][0]["id"] if r.status_code == 200 and r.json()["items"] else None
    rows.append(case("live: story list", "200 with stories",
                     f"{r.status_code}, {r.json().get('total')} stories", r.status_code == 200
                     and first is not None, trace="FR-09"))
    if first is not None:
        r = api.get(f"/api/stories/{first}")
        rows.append(case(f"live: story {first}", "200",
                         f"{r.status_code}, status {r.json().get('status')}, "
                         f"readability recorded {r.json().get('readability', {}).get('recorded')}",
                         r.status_code == 200, trace="FR-09"))
    # Before a story has a summary headline, its card and its page each fall back
    # to the newest article's: the same article, ties on publish time included.
    # Compared directly, since stories with a summary never fall back.
    with real.cursor() as cur:
        cur.execute(store_module.STORY_SQL, store_module.story_params())
        cards = cur.fetchall()
    differ = [c["id"] for c in cards
              if real.story(c["id"])["articles"][0]["title"] != c["latest_title"]]
    rows.append(case("live: a story card and its page fall back to the same headline",
                     "no story differs", f"{len(cards)} stories, "
                     f"{len(cards) - len(differ)} match, differ: {differ or 'none'}",
                     cards and not differ, trace="FR-09"))
    try:
        with real.cursor() as cur:
            cur.execute("CREATE TEMP TABLE api_write_probe (x int)")
        refused, detail = False, "the write succeeded"
    except Exception as exc:
        refused, detail = "read-only" in str(exc), f"{type(exc).__name__}: {str(exc).strip()}"
    rows.append(case("live: a write through the API's connection is refused",
                     "refused: read-only transaction", detail, refused, trace="NFR-03"))

    for path, what in [("/api/stories?limit=3&sort=differences", "items"),
                       ("/api/stories?limit=3&sort=latest", "items"),
                       ("/api/contested?limit=3", "items")]:
        r = api.get(path)
        rows.append(case(f"live: {path}", "200", f"{r.status_code}, "
                         f"{len(r.json().get(what, []))} stories", r.status_code == 200,
                         trace="FR-08"))
    r = api.get("/api/people")
    people = r.json() if r.status_code == 200 else []
    leaked = "records" in r.text
    rows.append(case("live: people list", "200, titles and tone, no stored mentions",
                     f"{r.status_code}, {len(people)} people, first "
                     f"{people[0]['name'] if people else '-'} ({people[0]['title'] if people else '-'}), "
                     f"{len(r.content) // 1024} KB, mentions {'included' if leaked else 'left out'}",
                     r.status_code == 200 and people and people[0]["tone"] and not leaked,
                     trace="FR-07"))
    r = api.get("/api/topics")
    rows.append(case("live: topics", "200 with topics", f"{r.status_code}, {len(r.json())} topics",
                     r.status_code == 200 and len(r.json()) > 0, trace="FR-08"))

    # a story too loose to compare has no page, so a search hit must not link to one
    if first is not None:
        title = api.get(f"/api/stories/{first}").json()["headline"][:200]
        r = api.get("/api/search", params={"q": title, "limit": 50})
        linked = {h["story_id"] for h in r.json().get("results", []) if h["story_id"]}
        opened = [api.get(f"/api/stories/{i}").status_code for i in sorted(linked)]
        rows.append(case("live: every story a search result links to opens",
                         "at least one story linked, 200 for each",
                         f"{r.status_code}; {len(linked)} linked, answers {sorted(set(opened))}",
                         r.status_code == 200 and linked and all(c == 200 for c in opened),
                         trace="FR-10"))
    with real.cursor() as cur:
        cur.execute("""
            SELECT a.id, a.title
            FROM cluster_members cm
            JOIN clusters c ON c.id = cm.cluster_id
            JOIN articles a ON a.id = cm.article_id
            WHERE c.coherence < %s AND a.embedding IS NOT NULL
            ORDER BY a.id LIMIT 1
        """, (CLUSTER_MIN_COHERENCE,))
        loose = cur.fetchone()
    if loose:
        r = api.get("/api/search", params={"q": loose["title"][:200], "limit": 50})
        hit = next((h for h in r.json().get("results", []) if h["id"] == loose["id"]), None)
        rows.append(case("live: an article in a story too loose to compare links to no story",
                         "found, story_id None",
                         f"{'found' if hit else 'not found'}, "
                         f"story_id {hit['story_id'] if hit else '-'}",
                         hit is not None and hit["story_id"] is None, trace="FR-10"))

    r = api.get("/api/sources")
    listed = r.json() if r.status_code == 200 else []
    names = [s["name"] for s in listed]
    share = sum(s["share"] for s in listed)
    rows.append(case("live: sources are the configured outlets, and only those",
                     f"200, {len(RSS_FEEDS)} outlets, shares adding to 1",
                     f"{r.status_code}, {len(listed)} outlets, shares adding to {share:.3f}",
                     r.status_code == 200 and sorted(names) == sorted(f["name"] for f in RSS_FEEDS)
                     and abs(share - 1) < 0.01, trace="FR-09"))
    if listed:
        top = listed[0]
        r = api.get(f"/api/sources/{top['slug']}")
        page = r.json() if r.status_code == 200 else {}
        covered = page.get("stories_covered", [])
        rows.append(case(f"live: source page for {top['name']}",
                         "200, newest headlines, and every story listed includes the outlet",
                         f"{r.status_code}, {len(page.get('recent', []))} headlines, "
                         f"{len(covered)} stories",
                         r.status_code == 200 and page.get("recent")
                         and all(top["name"] in s["outlets"] for s in covered), trace="FR-09"))
        r = api.get(f"/api/stories?source={top['slug']}&limit=20")
        items = r.json().get("items", []) if r.status_code == 200 else []
        rows.append(case(f"live: stories filtered by {top['name']}",
                         "200, every story includes the outlet",
                         f"{r.status_code}, {len(items)} stories, "
                         f"{sum(top['name'] in s['outlets'] for s in items)} include it",
                         r.status_code == 200 and items
                         and all(top["name"] in s["outlets"] for s in items), trace="FR-09"))
    r = api.get("/api/topics")
    topic = next((t["topic"] for t in r.json() if t["topic"] != "General"), None) \
        if r.status_code == 200 else None
    if topic:
        r = api.get("/api/stories", params={"topic": topic, "limit": 20})
        items = r.json().get("items", []) if r.status_code == 200 else []
        rows.append(case(f"live: stories filtered by topic {topic}",
                         f"200, every story is {topic}",
                         f"{r.status_code}, {len(items)} stories, topics "
                         f"{sorted({s['topic'] for s in items})}",
                         r.status_code == 200 and items
                         and all(s["topic"] == topic for s in items), trace="FR-09"))
    if first is not None:
        body = api.get(f"/api/stories/{first}").json()
        numbers = (body.get("analysis") or {}).get("numbers") or {}
        credits = [v["credited_to"] for g in numbers.get("groups", []) for v in g["values"]]
        credits += [v["credited_to"] for v in numbers.get("ungrouped", []) + numbers.get("solo", [])]
        rows.append(case(f"live: story {first} lays out its numbers and names its people",
                         "numbers in three sections, people listed, nothing credited to \"who\"",
                         f"sections {sorted(numbers)}, {len(body.get('people', []))} people, "
                         f"credits {sorted({c for c in credits if c})}",
                         sorted(numbers) == ["groups", "solo", "ungrouped"]
                         and isinstance(body.get("people"), list)
                         and "who" not in credits, trace="FR-06, FR-07"))
    rows.append(role_case())
    return rows


def role_case():
    """The API's account can read and not write. Created in a transaction that is
    always rolled back, so nothing is left in the database."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cur = conn.cursor()
        api_role.apply(cur, secrets.token_urlsafe(24))
        cur.execute(f"SET LOCAL ROLE {api_role.ROLE}")
        cur.execute("SELECT count(*) FROM articles")
        readable = cur.fetchone()[0] > 0
        refused = []
        for statement in ("INSERT INTO people (id) VALUES ('probe')",
                          "UPDATE articles SET title = title WHERE false",
                          "DELETE FROM clusters WHERE false",
                          "DROP TABLE people",
                          "CREATE TABLE api_role_probe (x int)"):
            cur.execute("SAVEPOINT probe")
            try:
                cur.execute(statement)
            except psycopg2.errors.InsufficientPrivilege:
                refused.append(statement.split()[0])
            cur.execute("ROLLBACK TO SAVEPOINT probe")
    finally:
        conn.rollback()
        conn.close()
    return case("live: the API's own account reads every table and writes none",
                "reads articles; refused INSERT, UPDATE, DELETE, DROP, CREATE",
                f"reads articles {readable}; refused {', '.join(refused)}",
                readable and refused == ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE"],
                trace="NFR-03")


# the API logs every unexpected error with its traceback, by design; the cases
# below provoke some on purpose, and the log would bury the results
logging.getLogger("newseye.api").setLevel(logging.CRITICAL)

if __name__ == "__main__":
    rows = results() + (live_results() if "--live" in sys.argv else [])
    sys.exit(report(rows, "API cases"))
