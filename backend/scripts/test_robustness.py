"""Do the edges hold: thresholds, failures, hostile input and empty input?

The other suites check that each component does its job on realistic input.
These check the edges around it:

    boundary    a value exactly at a threshold falls on the documented side
    exception   a database or feed that fails is reported, never a crash, and
                a degenerate clustering leaves the stored stories alone
    security    feed text is third-party input: markup in it is shown as text,
                and only http(s) links reach a reader
    empty       every analysis step given nothing returns nothing

None needs the database or the network. A failure is simulated by swapping in
a stand-in for the function that would have failed.

    python -m backend.scripts.test_robustness
"""
import io
import sys
from contextlib import contextmanager, redirect_stdout

import numpy as np

from backend.scripts.testkit import case, report


@contextmanager
def replaced(module, name, value):
    """module.name is value until the block ends: a dependency made to fail."""
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


def quietly(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


class FakeFeed(dict):
    """What feedparser returns: a dict whose keys also read as attributes."""

    def __getattr__(self, name):
        return self.get(name)


def story(title, articles, coherence=0.7):
    """The smallest cluster a story page can be built from."""
    return {"cluster_id": 1, "title_summary": title, "coherence": coherence,
            "retrieved": len(articles), "articles": articles, "consensus": [],
            "quotes": [], "framing": [], "figure_digest": [], "subject": None,
            "topic_label": "Politics"}


def article(source, title, url):
    return {"source": source, "title": title, "url": url, "fetched": True}


# --- boundary ----------------------------------------------------------------

def tone_threshold():
    from backend.analysis.framing import _frame_label
    got = {v: _frame_label(v) for v in (0.15, 0.151, -0.15, -0.151)}
    wanted = {0.15: "neutral", 0.151: "positive", -0.15: "neutral", -0.151: "negative"}
    words = lambda d: ", ".join(f"{k:+} {v}" for k, v in d.items())  # noqa: E731
    return case("[boundary] tone label at the +/-0.15 neutral band",
                words(wanted), words(got), got == wanted)


def tone_minimum():
    from backend.analysis.portrayal import TONE_MIN_SENTENCES, tone_summary
    short = tone_summary([0.5] * (TONE_MIN_SENTENCES - 1))
    enough = tone_summary([0.5] * TONE_MIN_SENTENCES)
    got = (f"{TONE_MIN_SENTENCES - 1}: {short['label'] if short else 'no tone given'}; "
           f"{TONE_MIN_SENTENCES}: {enough['label'] if enough else 'no tone given'}")
    return case(f"[boundary] headline tone needs {TONE_MIN_SENTENCES} sentences",
                f"{TONE_MIN_SENTENCES - 1}: no tone given; {TONE_MIN_SENTENCES}: leans positive",
                got, short is None and enough and enough["label"] == "leans positive")


def quote_minimum():
    from backend.analysis.quotes import extract_quotes
    from backend.config import QUOTE_MIN_WORDS
    short = " ".join(["word"] * (QUOTE_MIN_WORDS - 1)).capitalize()
    enough = " ".join(["word"] * QUOTE_MIN_WORDS).capitalize()
    found_short = extract_quotes(f"“{short},” Kindiki said on Tuesday.")
    found_enough = extract_quotes(f"“{enough},” Kindiki said on Tuesday.")
    got = (f"{QUOTE_MIN_WORDS - 1} words: {'quote' if found_short else 'no quote'}; "
           f"{QUOTE_MIN_WORDS} words: {'quote' if found_enough else 'no quote'}")
    return case(f"[boundary] a quote needs {QUOTE_MIN_WORDS} words",
                f"{QUOTE_MIN_WORDS - 1} words: no quote; {QUOTE_MIN_WORDS} words: quote",
                got, not found_short and bool(found_enough))


def continuity_share():
    from backend.nlp.clustering import match_clusters
    half = match_clusters({1: {10, 11, 12, 13}}, {0: {10, 11, 20, 21, 22}})
    under = match_clusters({1: {10, 11, 12, 13, 14}}, {0: {10, 11, 20, 21, 22}})
    got = (f"2 of 4 shared: {'keeps id' if half else 'fresh id'}; "
           f"2 of 5 shared: {'keeps id' if under else 'fresh id'}")
    return case("[boundary] a story keeps its id at exactly half shared",
                "2 of 4 shared: keeps id; 2 of 5 shared: fresh id", got,
                half == {0: 1} and under == {})


def coherence_floor():
    from backend.scripts.build_site import story_page
    pages = {c: story_page(story("A story", [article("KBC", "A", "https://kbc.co.ke/a"),
                                             article("Nation Africa", "B",
                                                     "https://nation.africa/b")],
                                 coherence=c), "2026-10-15")
             for c in (0.50, 0.49)}
    warned = {c: "not confident these are one story" in page for c, page in pages.items()}
    got = "; ".join(f"{c:.2f}: {'warning' if w else 'no warning'}" for c, w in warned.items())
    return case("[boundary] the loose-cluster warning starts below 0.50 coherence",
                "0.50: no warning; 0.49: warning", got,
                warned == {0.50: False, 0.49: True})


# --- exception ---------------------------------------------------------------

def database_down():
    import backend.passive as passive

    def unreachable():
        raise ConnectionError("could not connect to server")

    with replaced(passive, "_read_state", unreachable):
        try:
            code = quietly(passive.run, skip_ingest=True)
            got = f"exit code {code}"
        except Exception as exc:
            code, got = None, f"crashed: {type(exc).__name__}"
    return case("[exception] database unreachable when the scheduled run starts",
                "exit code 1, reported, no traceback", got, code == 1)


def feeds_down():
    import backend.ingestion.runner as runner
    from backend.config import RSS_FEEDS

    def dead(url):
        return FakeFeed(entries=[], bozo=True, status=404)

    with replaced(runner, "fetch_feed", dead):
        try:
            result = quietly(runner.run_ingestion)
            got = (f"{len(result['failed'])} of {len(RSS_FEEDS)} reported failed, "
                   f"{result['inserted']} inserted")
            ok = len(result["failed"]) == len(RSS_FEEDS) and result["inserted"] == 0
        except Exception as exc:
            got, ok = f"crashed: {type(exc).__name__}", False
    return case("[exception] every feed answers HTTP 404",
                f"{len(RSS_FEEDS)} of {len(RSS_FEEDS)} reported failed, 0 inserted", got, ok)


def degenerate_clustering():
    import backend.nlp.clustering as clustering

    rng = np.random.default_rng(0)
    base = rng.normal(size=384)
    # 30 near-identical articles and 10 unrelated: one cluster would hold 75%
    vectors = [base + rng.normal(scale=0.01, size=384) for _ in range(30)]
    vectors += [rng.normal(size=384) for _ in range(10)]
    rows = [{"id": i, "title": f"t{i}", "category": "Politics",
             "embedding": list(v / np.linalg.norm(v))} for i, v in enumerate(vectors)]
    saved = []
    with replaced(clustering, "load_articles", lambda days: rows), \
         replaced(clustering, "save_clusters", lambda *a, **k: saved.append(a)):
        try:
            quietly(clustering.run_clustering)
            got = "accepted"
        except clustering.DegenerateClustering:
            got = "rejected"
    got += f", stored stories {'overwritten' if saved else 'left alone'}"
    return case("[exception] one cluster swallows 75% of the window",
                "rejected, stored stories left alone", got,
                got == "rejected, stored stories left alone")


# --- security ----------------------------------------------------------------

def link_schemes():
    from backend.ingestion.dedupe import is_web_url
    urls = {"https://nation.africa/kenya/news": True, "HTTP://kbc.co.ke/a": True,
            "javascript:alert(1)": False, "  JavaScript:alert(1)": False,
            "data:text/html,<script>alert(1)</script>": False, "//evil.example": False,
            "": False}
    wrong = [u for u, safe in urls.items() if is_web_url(u) != safe]
    return case("[security] only http(s) counts as a web link",
                "http and https accepted; javascript:, data:, protocol-relative and "
                "empty rejected",
                "all as expected" if not wrong else f"misjudged: {wrong}", not wrong)


def hostile_feed_link():
    import backend.ingestion.runner as runner

    def hostile(url):
        return FakeFeed(entries=[{"title": "Click for the latest results",
                                  "link": "javascript:alert(document.cookie)"}],
                        bozo=False, status=200)

    inserted = []
    with replaced(runner, "fetch_feed", hostile), \
         replaced(runner, "existing_identifiers", lambda ids: set()), \
         replaced(runner, "insert_article", lambda *a: inserted.append(a) or 1):
        result = quietly(runner.run_ingestion)
    return case("[security] a feed item whose link is javascript:",
                "not stored", f"{len(inserted)} stored, {result['inserted']} counted",
                not inserted and result["inserted"] == 0)


def hostile_markup():
    from backend.scripts.build_site import story_page
    page = story_page(story("<img src=x onerror=alert(1)> Ruto speaks",
                            [article("KBC", "<script>alert(1)</script> Kindiki tours Embu",
                                     "javascript:alert(1)"),
                             article("Nation Africa", "Kindiki in Embu",
                                     "https://nation.africa/b")]), "2026-10-15")
    found = [bad for bad in ("<script>alert", "<img src=x", 'href="javascript:')
             if bad in page.lower()]
    return case("[security] a headline carrying markup and a javascript: link",
                "markup shown as text; the unsafe link not rendered",
                "clean" if not found else f"found {found}", not found)


# --- empty input -------------------------------------------------------------

def empty_inputs():
    from backend.analysis.consensus import analyze_cluster_claims
    from backend.analysis.divergence import differences
    from backend.analysis.framing import analyze_framing
    from backend.analysis.quotes import align_quotes, extract_quotes

    steps = [
        ("quote extraction", lambda: extract_quotes(""), [], "FR-05"),
        ("quote alignment", lambda: align_quotes([]), [], "FR-05"),
        ("coverage table", lambda: analyze_cluster_claims([], all_sources=[]), [], "FR-04"),
        ("framing", lambda: analyze_framing([]), [], "FR-07"),
        ("divergence score", lambda: differences({})["score"], 0, "FR-08"),
    ]
    rows = []
    for name, step, wanted, requirement in steps:
        try:
            got = step()
            actual, ok = repr(got), got == wanted
        except Exception as exc:
            actual, ok = f"crashed: {type(exc).__name__}: {exc}", False
        rows.append(case(f"[empty] {name} given nothing", repr(wanted), actual, ok,
                         trace=f"{requirement}, NFR-02"))
    return rows


# the requirement each edge case gives evidence for
TRACE = [
    (tone_threshold, "FR-07"), (tone_minimum, "FR-07"), (quote_minimum, "FR-05"),
    (continuity_share, "FR-02"), (coherence_floor, "FR-04, NFR-04"),
    (database_down, "NFR-02"), (feeds_down, "FR-01, NFR-02"),
    (degenerate_clustering, "FR-02, NFR-02"), (link_schemes, "NFR-03"),
    (hostile_feed_link, "FR-01, NFR-03"), (hostile_markup, "FR-09, NFR-03"),
]


def results():
    rows = []
    for check, requirement in TRACE:
        row = check()
        row["trace"] = requirement
        rows.append(row)
    return rows + empty_inputs()


if __name__ == "__main__":
    sys.exit(report(results(), "robustness cases"))
