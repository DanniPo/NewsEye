"""Run the core workflow once, from the RSS feeds to the published site, checking every hand-off.

Each component passes something to the next, and each hand-off is checked
against what it should contain:

    feeds    -> articles   every new article stored with an embedding and a topic
    articles -> clusters   the window re-clustered, ids carried over, every story summarised
    clusters -> analyses   the active tier on N stories: coverage, quotes, figures, framing
    analyses -> site       a page per story, the search index, people pages, a one-file copy

Ingest, cluster and summarise are the same three calls the scheduled passive tier
makes, and the analysis is the call the active tier makes. The stories analysed
are the ones this run's new articles joined, most outlets first, so the record
follows fresh input all the way to a page.

    python -m backend.scripts.end_to_end                  # 5 stories
    python -m backend.scripts.end_to_end --stories 8
    python -m backend.scripts.end_to_end --skip-ingest    # no feed polling

The site goes to dist/latest/ - never over the demonstration site - and the
record to docs/evidence/end-to-end-<date>.md. Exits 1 if any check failed.
"""
import argparse
import html
import json
import os
import re
import sys
import time
from datetime import UTC, datetime

from backend.config import CLUSTER_MIN_COHERENCE, RSS_FEEDS
from backend.db.connection import get_cursor
from backend.scripts.test_record import cell, environment

OUT_DIR = os.path.join("dist", "latest")
RECORD_DIR = os.path.join("docs", "evidence")
# headings every story page carries, whatever the story
STORY_SECTIONS = ("Headlines", "What each outlet reported", "The numbers")
LOCAL_LINK = re.compile(r'href="(?:index|people|search|story-\d+|person-[a-z0-9-]+)\.html')


# the requirement each stage's checks give evidence for (testkit.REQUIREMENTS)
STAGE_TRACE = {"Database": "NFR-02", "Ingest": "FR-01", "Cluster": "FR-02",
               "Analyse": "FR-04 to FR-07", "Publish": "FR-09"}


class Record:
    """The checks made so far, each with what was expected and what came out."""

    def __init__(self):
        self.checks, self.stages, self.notes, self.stories = [], [], [], []

    def check(self, stage, what, expected, actual, ok, trace=None):
        self.checks.append({"id": f"ST-{len(self.checks) + 1:02d}", "stage": stage,
                            "check": what, "expected": expected, "actual": actual,
                            "ok": bool(ok), "trace": trace or STAGE_TRACE[stage]})
        print(f"  {'PASS' if ok else 'FAIL'}  {what}: {actual}", flush=True)

    def note(self, text):
        self.notes.append(text)
        print(f"  note: {text}", flush=True)

    def stage(self, name, component, seconds):
        self.stages.append((name, component, seconds))


def count(n, noun, plural=None):
    return f"{n} {noun if n == 1 else plural or noun + 's'}"


def one(sql, params=()):
    with get_cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def ingest(record, started):
    print("\n-- ingest: RSS feeds -> PostgreSQL --", flush=True)
    mark = time.time()
    from backend.ingestion.runner import run_ingestion  # loads MiniLM and DeBERTa
    loaded = time.time() - mark
    record.stage("Model load", "torch, MiniLM, DeBERTa", loaded)
    mark = time.time()
    report = run_ingestion()
    record.stage("Ingest", "feedparser, SHA-256 dedupe, MiniLM embedding, DeBERTa topic",
                 time.time() - mark)

    failed = report["failed"]
    answered = len(RSS_FEEDS) - len(failed)
    record.check("Ingest", "Every outlet's feed answered", f"{len(RSS_FEEDS)} of {len(RSS_FEEDS)}",
                 f"{answered} of {len(RSS_FEEDS)}"
                 + (" - failed: " + ", ".join(f"{k} ({v})" for k, v in failed.items())
                    if failed else ""),
                 not failed)
    with get_cursor() as cur:
        cur.execute("""
            SELECT source_name, count(*) AS n,
                   count(*) FILTER (WHERE embedding IS NULL) AS no_vector,
                   count(*) FILTER (WHERE category IS NULL) AS no_topic
            FROM articles WHERE inserted_at_utc >= %s
            GROUP BY 1 ORDER BY 2 DESC
        """, (started,))
        rows = cur.fetchall()
    new = sum(r["n"] for r in rows)
    record.check("Ingest", "New articles saved to the database",
                 "as many rows as the feeds yielded new items",
                 f"{new} rows for {report['inserted']} new items, from {len(rows)} outlets",
                 new == report["inserted"])
    missing = sum(r["no_vector"] for r in rows)
    record.check("Ingest", "Each new article has a 384-number embedding", "0 missing",
                 f"{missing} missing of {new}", missing == 0)
    untopiced = sum(r["no_topic"] for r in rows)
    record.check("Ingest", "Each new article has a topic label", "0 missing",
                 f"{untopiced} missing of {new}", untopiced == 0)
    if not new:
        record.note("The feeds had nothing new since the last poll, so the stories "
                    "followed below are the richest in the window rather than fresh ones.")
    return new


def cluster(record, started):
    print("\n-- cluster: articles -> stories --", flush=True)
    from backend.nlp.clustering import DegenerateClustering, run_clustering
    from backend.nlp.previews import generate_previews

    mark = time.time()
    try:
        n_clusters, n_noise = run_clustering()
    except DegenerateClustering as exc:
        record.check("Cluster", "Clustering accepted", "a usable clustering",
                     f"rejected, previous clusters kept: {exc}", False)
        return False
    record.stage("Cluster", "HDBSCAN over the 7-day window, coherence, id continuity",
                 time.time() - mark)
    mark = time.time()
    generate_previews()
    record.stage("Summarise", "one extractive headline per story", time.time() - mark)

    window = one("""SELECT count(*) AS n FROM articles
                    WHERE published_utc >= now() - interval '7 days'
                      AND embedding IS NOT NULL""")["n"]
    stats = one("""
        SELECT count(*) AS n,
               count(*) FILTER (WHERE clustered_at >= %s) AS this_run,
               count(*) FILTER (WHERE created_at < %s) AS carried,
               count(*) FILTER (WHERE coherence IS NULL) AS no_coherence,
               count(*) FILTER (WHERE coherence >= %s) AS coherent
        FROM clusters
    """, (started, started, CLUSTER_MIN_COHERENCE))
    record.check("Cluster", "The window was re-clustered on this run",
                 "every stored story stamped by this run",
                 f"{stats['this_run']} of {stats['n']} stories ({n_noise} of the window's "
                 f"articles left as noise)", stats["this_run"] == stats["n"] > 0)
    record.check("Cluster", "Each story has a coherence score", "0 missing",
                 f"{stats['no_coherence']} missing", stats["no_coherence"] == 0)
    unsummarised = one("""
        SELECT count(*) AS n FROM clusters c
        LEFT JOIN cluster_analysis ca ON ca.cluster_id = c.id
        WHERE ca.title_summary IS NULL
    """)["n"]
    record.check("Cluster", "Each story has a summary headline", "0 missing",
                 f"{unsummarised} missing", unsummarised == 0)
    mismatched = one("""
        SELECT count(*) AS n FROM clusters c
        WHERE c.article_count <> (SELECT count(*) FROM cluster_members cm
                                  WHERE cm.cluster_id = c.id)
    """)["n"]
    record.check("Cluster", "Stored article counts match the memberships", "0 mismatched",
                 f"{mismatched} mismatched", mismatched == 0)
    doubled = one("""
        SELECT count(*) AS n FROM (
            SELECT article_id FROM cluster_members GROUP BY 1 HAVING count(*) > 1) x
    """)["n"]
    record.check("Cluster", "No article belongs to two stories", "0", f"{doubled}",
                 doubled == 0)
    joined = one("""
        SELECT count(DISTINCT cm.article_id) AS n FROM cluster_members cm
        JOIN articles a ON a.id = cm.article_id WHERE a.inserted_at_utc >= %s
    """, (started,))["n"]
    record.note(f"{n_clusters} stories from {window} articles in the window; "
                f"{stats['carried']} kept their id from an earlier run, "
                f"{n_clusters - stats['carried']} are new; {stats['coherent']} are at or "
                f"above the {CLUSTER_MIN_COHERENCE} coherence floor and can get a page; "
                f"{joined} of this run's new articles joined a story.")
    return True


def pick_stories(started, n):
    """Stories this run's new articles joined, most outlets first, topped up with the richest."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.id, count(DISTINCT a.source_name) AS outlets,
                   bool_or(a.inserted_at_utc >= %s) AS fresh
            FROM clusters c
            JOIN cluster_members cm ON cm.cluster_id = c.id
            JOIN articles a ON a.id = cm.article_id
            WHERE c.coherence >= %s
            GROUP BY c.id
            HAVING count(DISTINCT a.source_name) >= 2
            ORDER BY bool_or(a.inserted_at_utc >= %s) DESC,
                     count(DISTINCT a.source_name) DESC, c.id DESC
            LIMIT %s
        """, (started, CLUSTER_MIN_COHERENCE, started, n))
        return cur.fetchall()


def analyse(record, started, n):
    print("\n-- analyse: stories -> comparisons (active tier) --", flush=True)
    from backend.scripts.export_review import analyse as analyse_story

    picked = pick_stories(started, n)
    fresh = sum(1 for p in picked if p["fresh"])
    record.note(f"{count(len(picked), 'story', 'stories')} analysed, {fresh} of them joined "
                f"by this run's new articles"
                + (", the rest the richest in the window." if fresh < len(picked) else "."))
    bundle = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "clusters": [],
              "selection": None}
    mark = time.time()
    for story in picked:
        cid = story["id"]
        began = time.time()
        try:
            entry = analyse_story(cid)
        except Exception as exc:
            record.check("Analyse", f"Story {cid} analysed", "analysis completes",
                         f"{type(exc).__name__}: {exc}", False)
            continue
        if entry is None:
            record.check("Analyse", f"Story {cid} analysed", "analysis completes",
                         "story vanished before it could be analysed", False)
            continue
        seconds = time.time() - began
        outlets = {a["source"] for a in entry["articles"]}
        readable = {a["source"] for a in entry["articles"] if a["fetched"]}
        stored = one("""SELECT sources_used, analyzed_at, consensus
                        FROM cluster_analysis WHERE cluster_id = %s""", (cid,))
        facts = len(entry["consensus"] or [])
        saved = (stored is not None and stored["sources_used"] is not None
                 and stored["analyzed_at"] >= started
                 and len(stored["consensus"] or []) == facts)
        quotes = entry["quotes"] or []
        shared = sum(1 for q in quotes if q.get("outlets", 0) > 1)
        record.check("Analyse", f"Story {cid} analysed and saved",
                     "comparison saved to cluster_analysis on this run",
                     f"{count(facts, 'fact')} from {len(readable)} of {len(outlets)} outlets "
                     f"read; {count(len(quotes), 'quote')} ({shared} quoted by 2+ outlets); "
                     f"{count(len(entry['figure_digest'] or []), 'figure')}; "
                     f"{count(len(entry['framing'] or []), 'name')} compared for tone; "
                     f"{seconds:.1f}s", saved)
        record.stories.append({"id": cid, "title": entry["title_summary"] or "",
                               "outlets": len(outlets), "readable": len(readable),
                               "fresh": story["fresh"], "facts": facts,
                               "quotes": len(quotes), "figures": len(entry["figure_digest"] or [])})
        bundle["clusters"].append(entry)
    record.stage("Analyse", "fetch text, spaCy claims, MiniLM + NLI coverage, quotes, "
                            "figures, RoBERTa tone", time.time() - mark)
    return bundle


def publish(record, bundle, out_dir):
    print("\n-- publish: comparisons -> static site --", flush=True)
    from backend.scripts.build_site import build
    from backend.scripts.single_file import bundle as fold

    mark = time.time()
    os.makedirs(out_dir, exist_ok=True)
    export = os.path.join(out_dir, "export.json")
    with open(export, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=1, default=str)
    site = os.path.join(out_dir, "site")
    build(export, site)
    record.stage("Publish", "static HTML pages, search index, people pages", time.time() - mark)

    pages = set(os.listdir(site))
    dashboard = open(os.path.join(site, "index.html"), encoding="utf-8").read()
    for entry, story in zip(bundle["clusters"], record.stories, strict=True):
        name = f"story-{entry['cluster_id']}.html"
        readable = {a["source"] for a in entry["articles"] if a["fetched"]}
        if len(readable) < 2 or not entry["consensus"]:
            # nothing to set side by side: by design no page, never an empty one
            record.check("Publish", f"Story {entry['cluster_id']} has no page",
                         "no page: fewer than two outlets could be read",
                         "no page" if name not in pages else "a page was built",
                         name not in pages)
            story["page"] = "none (fewer than two outlets readable)"
            continue
        if name not in pages:
            record.check("Publish", f"Story {entry['cluster_id']} page", "page written",
                         "no page", False)
            story["page"] = "missing"
            continue
        page = open(os.path.join(site, name), encoding="utf-8").read()
        sections = [s for s in STORY_SECTIONS if s in page]
        linked = sum(1 for a in entry["articles"] if html.escape(a["url"]) in page)
        on_dashboard = f'href="{name}"' in dashboard
        record.check("Publish", f"Story {entry['cluster_id']} page",
                     f"all {len(STORY_SECTIONS)} sections, a link to every article, "
                     f"listed on the dashboard",
                     f"{len(sections)} of {len(STORY_SECTIONS)} sections; "
                     f"{linked} of {len(entry['articles'])} articles linked; "
                     f"{'on' if on_dashboard else 'NOT on'} the dashboard",
                     len(sections) == len(STORY_SECTIONS) and on_dashboard
                     and linked == len(entry["articles"]))
        story["page"] = name

    index_path = os.path.join(site, "search-index.js")
    if os.path.exists(index_path):
        text = open(index_path, encoding="utf-8").read()
        indexed = json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))["count"]
    else:
        indexed = 0
    in_db = one("SELECT count(DISTINCT url) AS n FROM articles WHERE embedding IS NOT NULL")["n"]
    record.check("Publish", "Search index covers the database",
                 f"all {in_db:,} articles", f"{indexed:,} articles", indexed == in_db,
                 trace="FR-10")

    people = sorted(p for p in pages if p.startswith("person-"))
    listed = 0
    if "people.html" in pages:
        listed = open(os.path.join(site, "people.html"), encoding="utf-8").read().count(
            'href="person-')
    record.check("Publish", "A page for every person on the People index",
                 "pages = people listed, at least one",
                 f"{len(people)} pages, {listed} listed", len(people) == listed > 0,
                 trace="FR-07, FR-09")

    single = os.path.join(out_dir, "newseye-latest.html")
    folded, size = fold(site, single)
    stray = len(LOCAL_LINK.findall(open(single, encoding="utf-8").read()))
    record.check("Publish", "One-file copy for sending",
                 "every page folded in, no links to separate files",
                 f"{folded} pages, {size / 1e6:.1f} MB, {stray} links to separate files",
                 folded == len([p for p in pages if p.endswith(".html")]) and stray == 0)
    record.stage("Bundle", "one self-contained HTML file", time.time() - mark
                 - record.stages[-1][2])


def render(record, env, began, seconds, out_dir):
    passed = sum(1 for c in record.checks if c["ok"])
    tree = " (with uncommitted changes)" if env["dirty"] else ""
    lines = [
        f"# End-to-end run - {began:%Y-%m-%d %H:%M}",
        "",
        f"Commit `{env['commit']}`{tree} · Python {env['python']} · torch {env['torch']} "
        f"on {env['device']} · {seconds / 60:.1f} minutes",
        "",
        f"**{passed} of {len(record.checks)} checks passed.** Input: the RSS feeds of "
        f"{len(RSS_FEEDS)} Kenyan outlets. Output: `{out_dir}/site/` and the one-file copy "
        f"`{out_dir}/newseye-latest.html`.",
        "",
        "Regenerate with `python -m backend.scripts.end_to_end`. Every stage runs the "
        "production code: the same calls the scheduled passive tier and the active tier make.",
        "",
        "## Stages",
        "",
        "| Stage | Components | Time |",
        "|---|---|---|",
    ]
    lines += [f"| {name} | {cell(component)} | {secs:.1f}s |"
              for name, component, secs in record.stages]
    lines += ["", "## Checks at each hand-off", "",
              "System test: the whole pipeline on live data, black-box at each hand-off "
              "between components.", "",
              "| Test ID | Traces to | Stage | Check | Expected | Actual | Verdict |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {c['id']} | {c['trace']} | {c['stage']} | {cell(c['check'])} | "
              f"{cell(c['expected'])} | {cell(c['actual'])} | "
              f"{'PASS' if c['ok'] else 'FAIL'} |" for c in record.checks]
    if record.stories:
        lines += ["", "## Stories followed from feed to page", "",
                  "| Story | Headline | Outlets (read) | New this run | Facts | Quotes | "
                  "Figures | Page |", "|---|---|---|---|---|---|---|---|"]
        lines += [f"| {s['id']} | {cell(s['title'])} | {s['outlets']} ({s['readable']}) | "
                  f"{'yes' if s['fresh'] else 'no'} | {s['facts']} | {s['quotes']} | "
                  f"{s['figures']} | {cell(s.get('page', ''))} |" for s in record.stories]
    if record.notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in record.notes]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stories", type=int, default=5)
    parser.add_argument("--skip-ingest", action="store_true",
                        help="do not poll the feeds; start from the stored articles")
    parser.add_argument("--out", default=OUT_DIR)
    parser.add_argument("--record", default=None)
    args = parser.parse_args()

    began = datetime.now()
    started = datetime.now(UTC)
    mark = time.time()
    record = Record()
    print(f"=== Newseye end-to-end run | {began:%Y-%m-%d %H:%M} ===")
    try:
        before = one("SELECT count(*) AS n FROM articles")["n"]
    except Exception as exc:
        record.check("Database", "PostgreSQL reachable", "connected",
                     f"{type(exc).__name__}: {exc}", False)
        before = None
    if before is not None:
        record.check("Database", "PostgreSQL reachable", "connected",
                     f"connected, {before:,} articles stored", True)
        if args.skip_ingest:
            record.note("Feeds not polled (--skip-ingest): the run starts from the stored "
                        "articles.")
        else:
            ingest(record, started)
        if cluster(record, started):
            bundle = analyse(record, started, args.stories)
            if bundle["clusters"]:
                publish(record, bundle, args.out)

    env = environment()
    text = render(record, env, began, time.time() - mark, args.out.replace(os.sep, "/"))
    out = args.record or os.path.join(RECORD_DIR, f"end-to-end-{began:%Y-%m-%d}.md")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, out)

    passed = sum(1 for c in record.checks if c["ok"])
    print(f"\n{passed}/{len(record.checks)} checks passed in {(time.time() - mark) / 60:.1f} min")
    print(f"Record written to {out}")
    return 0 if passed == len(record.checks) else 1


if __name__ == "__main__":
    sys.exit(main())
