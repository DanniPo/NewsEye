"""Does the web API answer correctly, refuse bad input and fail safely?

Black-box tests through FastAPI's test client against a fake data layer, so no
database is needed: routes, input validation, error codes, what an error reveals,
CORS and the read-only guarantees. --live adds checks against the real
database, including that a write through the API's connection is refused.

    python -m backend.scripts.test_api
    python -m backend.scripts.test_api --live
"""
import logging
import sys
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.api import store as store_module
from backend.api.main import app, get_store
from backend.api.store import READ_ONLY, DatabaseUnavailable, NotBuilt, NotPublished, clean
from backend.scripts.testkit import case, report

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
DIFF = {"score": 2, "reasons": ["outlets worded 1 fact differently",
                                "1 quote shortened or reworded"]}
SUMMARY = {"id": 903, "headline": "Ruto accuses Kenyatta of betrayal", "topic": "Politics",
           "outlets": ["Capital FM", "KBC", "Nairobi Wire"], "article_count": 7,
           "coherence": 0.71, "latest": NOW, "status": "analysed", "analysed_at": NOW,
           "differences": DIFF}
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
                      "differences": DIFF}}
PERSON = {"id": "william-ruto", "name": "William Ruto", "aliases": ["Ruto"], "articles": 567,
          "outlets": {"KBC": {"articles": 39}}, "totals": {"KBC": 464},
          "period_first": NOW, "period_last": NOW, "built_at": NOW}


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

    def stories(self, limit, offset, min_outlets):
        self._check("stories")
        return 1, [SUMMARY][:limit]

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
                 "outlets": 10, "built_at": NOW}]

    def person(self, person_id, records=20):
        self._check("person")
        return PERSON if person_id == "william-ruto" else None


def client(fake):
    app.dependency_overrides[get_store] = lambda: fake
    return TestClient(app, raise_server_exceptions=False)


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

    r = get(FakeStore(), "/api/people/william-ruto")
    check("person page", "200, William Ruto, 567 articles",
          f"{r.status_code}, {r.json().get('name')}, {r.json().get('articles')} articles",
          r.status_code == 200 and r.json()["articles"] == 567, "FR-07")

    # --------------------------------------------------------- refused input
    for path, why in [("/api/stories?limit=0", "limit below 1"),
                      ("/api/stories?limit=101", "limit above 100"),
                      ("/api/stories?offset=-1", "negative offset"),
                      ("/api/stories/abc", "story id not a number"),
                      ("/api/stories/0", "story id below 1"),
                      ("/api/search?q=a", "query of one character"),
                      ("/api/search?q=" + "x" * 201, "query over 200 characters"),
                      ("/api/search?q=%20%20%20", "query of spaces only"),
                      ("/api/people/Robert';DROP%20TABLE%20people;--", "person id with SQL")]:
        fake = FakeStore()
        r = get(fake, path)
        reached = [c for c in fake.calls if c in ("story", "search", "person", "stories")]
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

    check("database sessions are read-only, with a statement timeout",
          "default_transaction_read_only=on and statement_timeout",
          READ_ONLY, "default_transaction_read_only=on" in READ_ONLY
          and "statement_timeout" in READ_ONLY, "NFR-03")

    raw = '<p><a href="https://thekenyatimes.com" rel="nofollow">The Kenya Times</a> Ruto &amp; Raila'
    check("snippets reach the client as plain text (DEF-39)", "The Kenya Times Ruto & Raila",
          clean(raw), clean(raw) == "The Kenya Times Ruto & Raila", "NFR-03")

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
    try:
        with real.cursor() as cur:
            cur.execute("CREATE TEMP TABLE api_write_probe (x int)")
        refused, detail = False, "the write succeeded"
    except Exception as exc:
        refused, detail = "read-only" in str(exc), f"{type(exc).__name__}: {str(exc).strip()}"
    rows.append(case("live: a write through the API's connection is refused",
                     "refused: read-only transaction", detail, refused, trace="NFR-03"))
    return rows


# the API logs every unexpected error with its traceback, by design; the cases
# below provoke some on purpose, and the log would bury the results
logging.getLogger("newseye.api").setLevel(logging.CRITICAL)

if __name__ == "__main__":
    rows = results() + (live_results() if "--live" in sys.argv else [])
    sys.exit(report(rows, "API cases"))
