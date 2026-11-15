"""Newseye's read-only web API: stories, people, sources and search, for the React
interface in frontend/.

    uvicorn backend.api.main:app --reload       # then open http://127.0.0.1:8000/docs

It serves what the pipeline has already stored and computes nothing heavy per
request: the only model it runs is MiniLM, to embed a search query (the first
search loads it, which takes a few seconds). Nothing here writes, and the
database session is read-only (see store.py).

Not yet here, and needed before any public deployment: logins and roles (who
logs in is still to be agreed). Set up by the environment:

    NEWSEYE_API_ORIGINS        browser origins allowed to call the API, comma-separated;
                               the default is the Vite development server
    NEWSEYE_API_DB_USER,       the API's own read-only database account
    NEWSEYE_API_DB_PASSWORD    (python -m backend.db.api_role creates it)
    NEWSEYE_API_RATE,          requests a minute from one client, for everything and
    NEWSEYE_API_SEARCH_RATE    for search, which runs a model; default 120 and 30
"""
import logging
import os
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.api.store import SOURCES, DatabaseUnavailable, NotBuilt, NotPublished, Store
from backend.config import FALLBACK_LABEL, TOPIC_LABELS

log = logging.getLogger("newseye.api")

# the topics a story can carry; "General" is the label for none of the others
TOPICS = (*TOPIC_LABELS, FALLBACK_LABEL)
# an outlet in a link: "the-kenya-times"
SLUG = r"^[a-z0-9-]{1,60}$"

ORIGINS = [o.strip() for o in
           os.environ.get("NEWSEYE_API_ORIGINS", "http://localhost:5173").split(",")
           if o.strip()]
# the API returns JSON, so nothing in a response may load or be framed; the
# interactive docs load their page from a CDN, so they are left out
CONTENT_POLICY = "default-src 'none'; frame-ancestors 'none'"
DOCS = ("/docs", "/redoc")


# ---------------------------------------------------------------- responses
class Health(BaseModel):
    status: str
    articles: int
    stories: int
    analysed: int
    people: int | None
    last_article: datetime | None
    last_clustered: datetime | None


class Differences(BaseModel):
    score: int
    reasons: list[str]


class StorySummary(BaseModel):
    id: int
    headline: str | None
    topic: str | None
    outlets: list[str]
    article_count: int | None
    coherence: float | None
    latest: datetime | None
    status: str
    analysed_at: datetime | None
    differences: Differences | None
    facts_not_in_every_outlet: int | None
    numbers_to_compare: int | None
    unread_outlets: list[str] | None
    comparable: bool | None


class StoryPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[StorySummary]


class Contention(BaseModel):
    score: float
    reasons: list[str]


class ContestedStory(StorySummary):
    contention: Contention


class ContestedPage(BaseModel):
    days: int
    until: datetime | None
    items: list[ContestedStory]


class Topic(BaseModel):
    topic: str
    stories: int


class Readability(BaseModel):
    recorded: bool
    readable_outlets: list[str] | None
    unread_outlets: list[str] | None


class Article(BaseModel):
    id: int
    outlet: str
    title: str
    url: str
    published: datetime | None
    snippet: str | None
    readable: bool | None


class Figure(BaseModel):
    figure: str | None
    value: float | None
    unit: str | None
    source: str | None
    credited_to: str | None
    cumulative: bool
    currency: str | None
    breakdown: list[str]
    sentence: str
    context: str
    url: str | None


class FigureGroup(BaseModel):
    unit: str
    sources: list[str]
    values: list[Figure]


class Numbers(BaseModel):
    """A story's figures laid out for reading: groups that count the same thing,
    then figures that cannot be set beside another (see store.number_sections)."""
    groups: list[FigureGroup]
    ungrouped: list[Figure]
    solo: list[Figure]


class Analysis(BaseModel):
    coverage: list[Any]
    quotes: list[Any]
    figures: list[Any]
    framing: list[Any]
    differences: Differences
    numbers: Numbers


class NamedPerson(BaseModel):
    id: str
    name: str


class Story(BaseModel):
    id: int
    headline: str | None
    topic: str | None
    subject: str | None
    coherence: float | None
    article_count: int | None
    outlets: list[str]
    clustered_at: datetime | None
    status: str
    analysed_at: datetime | None
    readability: Readability
    articles: list[Article]
    analysis: Analysis | None
    people: list[NamedPerson]


class SearchHit(BaseModel):
    id: int
    title: str
    outlet: str
    url: str
    published: datetime | None
    snippet: str | None
    story_id: int | None
    similarity: float


class SearchResults(BaseModel):
    query: str
    results: list[SearchHit]


class Tone(BaseModel):
    """Shares of a person's headlines and opening lines; an automatic reading."""
    n: int
    negative: float
    positive: float


class PersonSummary(BaseModel):
    id: str
    name: str
    articles: int
    outlets: int
    built_at: datetime
    title: str | None
    tone: Tone | None
    never_named_by: list[str]


class Person(BaseModel):
    id: str
    name: str
    aliases: list[str]
    articles: int
    outlets: dict[str, Any]
    totals: dict[str, int]
    period_first: datetime | None
    period_last: datetime | None
    built_at: datetime


class Opened(BaseModel):
    """In how many analysed stories this outlet's article could be opened."""
    read: int
    unread: int


class SourceTopic(BaseModel):
    topic: str
    articles: int


class SourceSummary(BaseModel):
    slug: str
    name: str
    website: str | None
    note: str | None
    articles: int
    share: float
    first: datetime | None
    latest: datetime | None
    stories: int
    opened: Opened | None
    topics: list[SourceTopic]


class Headline(BaseModel):
    id: int
    title: str
    url: str
    published: datetime | None
    snippet: str | None
    story_id: int | None


class Source(SourceSummary):
    recent: list[Headline]
    stories_covered: list[StorySummary]


# ---------------------------------------------------------------- rate limits
class RateLimiter:
    """At most so many requests from one client in any 60 seconds.

    Counted in this process, which is enough for one API process; several would
    each count separately. Behind a proxy, run uvicorn with --proxy-headers so the
    client is the reader and not the proxy.
    """
    WINDOW = 60
    MAX_TRACKED = 10_000

    def __init__(self, per_minute, search_per_minute, clock=time.monotonic):
        self.limits = {"all": max(1, per_minute), "search": max(1, search_per_minute)}
        self.clock = clock
        self._hits = {}
        self._lock = threading.Lock()

    def wait(self, client, bucket):
        """Seconds before this client may try again; 0 lets it through and counts it."""
        now = self.clock()
        with self._lock:
            if len(self._hits) > self.MAX_TRACKED:
                self._hits = {k: h for k, h in self._hits.items() if h[-1] > now - self.WINDOW}
            hits = self._hits.setdefault((client, bucket), deque())
            while hits and hits[0] <= now - self.WINDOW:
                hits.popleft()
            if len(hits) >= self.limits[bucket]:
                return int(hits[0] + self.WINDOW - now) + 1
            hits.append(now)
            return 0


_limiter = RateLimiter(int(os.environ.get("NEWSEYE_API_RATE", "120")),
                       int(os.environ.get("NEWSEYE_API_SEARCH_RATE", "30")))


def get_limiter():
    """The rate limiter; the tests swap in their own."""
    return _limiter


LimiterDep = Annotated[RateLimiter, Depends(get_limiter)]


def _enforce(request, limiter, bucket):
    client = request.client.host if request.client else "unknown"
    wait = limiter.wait(client, bucket)
    if wait:
        raise HTTPException(status_code=429, detail="Too many requests: try again shortly",
                            headers={"Retry-After": str(wait)})


def rate_limit(request: Request, limiter: LimiterDep):
    _enforce(request, limiter, "all")


def search_rate_limit(request: Request, limiter: LimiterDep):
    _enforce(request, limiter, "search")


# ---------------------------------------------------------------- the app
def _warm_search():
    """Load MiniLM before the first search asks for it (it takes ~15 s)."""
    try:
        from backend.nlp.search import embed_query
        embed_query("warm up")
        log.info("search model loaded")
    except Exception:
        log.exception("could not load the search model; search will retry on first use")


@asynccontextmanager
async def lifespan(app):
    # in the background, so the API answers everything else at once;
    # NEWSEYE_API_WARM=0 skips it
    if os.environ.get("NEWSEYE_API_WARM", "1") == "1":
        threading.Thread(target=_warm_search, daemon=True).start()
    yield


app = FastAPI(title="Newseye API", version="0.3.0", lifespan=lifespan,
              dependencies=[Depends(rate_limit)],
              description="Read-only access to Newseye's stories, people, sources and "
                          "search. It reports what each outlet published; it gives no "
                          "verdicts.")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET"],
                   allow_headers=[], expose_headers=["Retry-After"])

_store = Store()


def get_store():
    """The data layer; the tests swap in a fake."""
    return _store


StoreDep = Annotated[Store, Depends(get_store)]


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if not request.url.path.startswith(DOCS):
        response.headers["Content-Security-Policy"] = CONTENT_POLICY
    return response


@app.exception_handler(DatabaseUnavailable)
async def database_unavailable(request: Request, exc: DatabaseUnavailable):
    log.warning("database unavailable: %r", exc.__cause__)
    return JSONResponse({"detail": "Database unavailable"}, status_code=503)


@app.exception_handler(NotBuilt)
async def not_built(request: Request, exc: NotBuilt):
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(NotPublished)
async def not_published(request: Request, exc: NotPublished):
    return JSONResponse({"detail": "This story has no page: its articles are too loosely "
                                   "related to compare"}, status_code=404)


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    # the cause goes to the server log, never to the client
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Internal error"}, status_code=500)


@app.get("/api/health", response_model=Health)
def health(store: StoreDep):
    return {"status": "ok", **store.health()}


@app.get("/api/stories", response_model=StoryPage)
def stories(store: StoreDep, limit: int = Query(20, ge=1, le=100),
            offset: int = Query(0, ge=0, le=100_000), min_outlets: int = Query(2, ge=1, le=12),
            sort: Literal["outlets", "differences", "latest"] = "outlets",
            topic: str | None = Query(None, max_length=40),
            source: str | None = Query(None, pattern=SLUG)):
    """Stories covered by at least min_outlets outlets, ordered by most outlets, most
    checkable differences, or newest article; only one topic's, or only those one
    outlet covered (by its slug, as /api/sources lists it), when asked."""
    if topic is not None and topic not in TOPICS:
        raise HTTPException(status_code=422, detail="Unknown topic")
    outlet = None
    if source is not None:
        outlet = SOURCES.get(source)
        if outlet is None:
            raise HTTPException(status_code=422, detail="Unknown source")
    total, items = store.stories(limit, offset, min_outlets, sort, topic=topic, source=outlet)
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/api/contested", response_model=ContestedPage)
def contested(store: StoreDep, limit: int = Query(20, ge=1, le=100),
              days: int = Query(7, ge=1, le=90)):
    """The latest stories whose coverage reports a dispute, most contested first, each
    with what was counted. What the stories report, not which outlet is right."""
    return store.contested(limit, days)


@app.get("/api/topics", response_model=list[Topic])
def topics(store: StoreDep):
    """How many multi-outlet stories each topic has."""
    return store.topics()


@app.get("/api/stories/{story_id}", response_model=Story)
def story(store: StoreDep, story_id: int = Path(ge=1)):
    """One story: its articles, which outlets could be read, and the comparison."""
    found = store.story(story_id)
    if found is None:
        raise HTTPException(status_code=404, detail="No such story")
    return found


@app.get("/api/search", response_model=SearchResults,
         dependencies=[Depends(search_rate_limit)])
def search(store: StoreDep, q: str = Query(min_length=2, max_length=200),
           limit: int = Query(20, ge=1, le=50)):
    """Articles closest in meaning to q."""
    query = " ".join(q.split())
    if len(query) < 2:
        raise HTTPException(status_code=422, detail="Query too short")
    return {"query": query, "results": store.search(query, limit)}


@app.get("/api/people", response_model=list[PersonSummary])
def people(store: StoreDep):
    """Everyone named often enough to compare, most articles first."""
    return store.people()


@app.get("/api/people/{person_id}", response_model=Person)
def person(store: StoreDep, person_id: str = Path(pattern=r"^[a-z0-9-]{1,80}$"),
           records: int = Query(20, ge=0, le=1000)):
    """How each outlet presents one person, with each outlet's newest mentions."""
    found = store.person(person_id, records)
    if found is None:
        raise HTTPException(status_code=404, detail="No such person")
    return found


@app.get("/api/sources", response_model=list[SourceSummary])
def sources(store: StoreDep):
    """Every outlet Newseye reads, most articles first: how much it has published
    here, how many stories it shares with other outlets, how often its articles
    could be opened, and its leading topics. Counts, not ratings."""
    return store.sources()


@app.get("/api/sources/{source_slug}", response_model=Source)
def source(store: StoreDep, source_slug: str = Path(pattern=SLUG),
           stories: int = Query(10, ge=0, le=50), recent: int = Query(12, ge=0, le=50)):
    """One outlet: its counts and topic mix, its newest headlines and its newest
    stories covered by other outlets too."""
    name = SOURCES.get(source_slug)
    found = store.source(name, stories, recent) if name else None
    if found is None:
        raise HTTPException(status_code=404, detail="No such source")
    return found
