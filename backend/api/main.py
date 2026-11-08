"""Newseye's read-only web API: stories, people and search, for the React interface.

    uvicorn backend.api.main:app --reload       # then open http://127.0.0.1:8000/docs

It serves what the pipeline has already stored and computes nothing heavy per
request: the only model it runs is MiniLM, to embed a search query (the first
search loads it, which takes a few seconds). Nothing here writes, and the
database session is read-only (see store.py).

Not yet here, and needed before any public deployment: logins and roles (who
logs in is still to be agreed), rate limits, and a SELECT-only database role.
NEWSEYE_API_ORIGINS lists the browser origins allowed to call the API,
comma-separated; the default is the Vite development server.
"""
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.api.store import DatabaseUnavailable, NotBuilt, NotPublished, Store

log = logging.getLogger("newseye.api")

ORIGINS = [o.strip() for o in
           os.environ.get("NEWSEYE_API_ORIGINS", "http://localhost:5173").split(",")
           if o.strip()]


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


class StoryPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[StorySummary]


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


class Analysis(BaseModel):
    coverage: list[Any]
    quotes: list[Any]
    figures: list[Any]
    framing: list[Any]
    differences: Differences


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


class PersonSummary(BaseModel):
    id: str
    name: str
    articles: int
    outlets: int
    built_at: datetime


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


app = FastAPI(title="Newseye API", version="0.1.0", lifespan=lifespan,
              description="Read-only access to Newseye's stories, people and search. "
                          "It reports what each outlet published; it gives no verdicts.")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET"],
                   allow_headers=[])

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
            offset: int = Query(0, ge=0, le=100_000), min_outlets: int = Query(2, ge=1, le=12)):
    """Stories covered by at least min_outlets outlets, most outlets first."""
    total, items = store.stories(limit, offset, min_outlets)
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/api/stories/{story_id}", response_model=Story)
def story(store: StoreDep, story_id: int = Path(ge=1)):
    """One story: its articles, which outlets could be read, and the comparison."""
    found = store.story(story_id)
    if found is None:
        raise HTTPException(status_code=404, detail="No such story")
    return found


@app.get("/api/search", response_model=SearchResults)
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
