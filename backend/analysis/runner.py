"""Active tier: on-demand deep analysis of one cluster, cached in the database.

Two stages share one cluster. The preview picks a representative headline and
lands in about a second; the deep pass fetches article text transiently, derives
coverage, figures and framing, stores only those derived results, and discards
the text. `clusters.analysis_status` says which stage a cluster has reached, so a
caller can show the preview while the deep pass is still running.

Every output is something for a reader to interpret - which outlet carried which
fact, which numbers each gave and in what words, how each described the people
involved. None of it is a verdict on who is right.
"""
import json
import sys
import time

from backend.analysis.claims import extract_claims
from backend.analysis.consensus import analyze_cluster_claims
from backend.analysis.digest import build_digest, digest_groups, summarise
from backend.analysis.framing import analyze_framing, describe_framing
from backend.analysis.story import representative_title
from backend.analysis.subject import derive_subject
from backend.config import (
    ANALYSIS_DEEP_READY,
    ANALYSIS_FAILED,
    ANALYSIS_MAX_ARTICLES,
    ANALYSIS_PREVIEW_READY,
    CLUSTER_MIN_COHERENCE,
    SENTIMENT_MODEL,
    TITLE_SUMMARY_MODEL,
)
from backend.db.connection import get_cursor
from backend.ingestion.fetch import fetch_many


def load_cluster(cluster_id):
    with get_cursor() as cur:
        cur.execute("SELECT id, topic_label, article_count, coherence "
                    "FROM clusters WHERE id = %s", (cluster_id,))
        cluster = cur.fetchone()
        if not cluster:
            return None, []
        cur.execute("""
            SELECT a.id, a.title, a.url, a.snippet, a.source_name, a.published_utc
            FROM cluster_members cm
            JOIN articles a ON a.id = cm.article_id
            WHERE cm.cluster_id = %s
            ORDER BY a.published_utc DESC NULLS LAST
            LIMIT %s
        """, (cluster_id, ANALYSIS_MAX_ARTICLES))
        return cluster, cur.fetchall()

def cached_analysis(cluster_id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM cluster_analysis WHERE cluster_id = %s", (cluster_id,))
        return cur.fetchone()

class ClusterNotFound(Exception):
    """Raised instead of SystemExit: a background worker must survive a bad id."""

def set_status(cluster_id, status, error=None):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE clusters SET analysis_status = %s, analysis_error = %s WHERE id = %s",
            (status, error, cluster_id)
        )

def mark_preview_ready(cluster_id):
    # refreshing a preview must not walk a finished cluster back a stage
    with get_cursor() as cur:
        cur.execute(
            "UPDATE clusters SET analysis_status = %s, analysis_error = NULL "
            "WHERE id = %s AND analysis_status <> %s",
            (ANALYSIS_PREVIEW_READY, cluster_id, ANALYSIS_DEEP_READY)
        )

def save_preview(cluster_id, title_summary):
    # writes only the preview columns, so it never overwrites a deep summary
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO cluster_analysis (cluster_id, title_summary, title_summary_at, summary_model)
            VALUES (%s, %s, now(), %s)
            ON CONFLICT (cluster_id) DO UPDATE SET
                title_summary = EXCLUDED.title_summary,
                title_summary_at = now(),
                summary_model = EXCLUDED.summary_model
        """, (cluster_id, title_summary, TITLE_SUMMARY_MODEL))

def save_analysis(cluster_id, result, sources_used):
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO cluster_analysis
                (cluster_id, consensus, subject,
                 framing, figure_digest, sources_used,
                 summary_model, sentiment_model, analyzed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (cluster_id) DO UPDATE SET
                consensus = EXCLUDED.consensus,
                subject = EXCLUDED.subject,
                framing = EXCLUDED.framing,
                figure_digest = EXCLUDED.figure_digest,
                sources_used = EXCLUDED.sources_used,
                summary_model = EXCLUDED.summary_model,
                sentiment_model = EXCLUDED.sentiment_model,
                analyzed_at = now()
        """, (cluster_id,
              # claims carry publication timestamps, so every jsonb write needs
              # a serialiser for datetime
              json.dumps(result["consensus"], default=str), result["subject"],
              json.dumps(result.get("framing") or [], default=str),
              json.dumps(result.get("figure_digest") or [], default=str),
              sources_used, TITLE_SUMMARY_MODEL, SENTIMENT_MODEL))

def preview_cluster(cluster_id, refresh=False):
    """Fast path: titles only, no fetching. Meant to return inside a web request."""
    if not refresh:
        cached = cached_analysis(cluster_id)
        if cached and cached.get("title_summary"):
            return cached["title_summary"]

    started = time.time()
    cluster, articles = load_cluster(cluster_id)
    if not cluster:
        raise ClusterNotFound(f"Cluster {cluster_id} not found")

    title_summary = representative_title([a["title"] for a in articles])
    save_preview(cluster_id, title_summary)
    mark_preview_ready(cluster_id)
    print(f"Preview for cluster {cluster_id} in {time.time() - started:.1f}s")
    return title_summary

def analyze_cluster(cluster_id, refresh=False):
    if not refresh:
        cached = cached_analysis(cluster_id)
        # sources_used is the marker for "the deep pass has run": it is the
        # count of articles actually fetched, and only save_analysis writes it.
        # This used to be `stances IS NOT NULL`, which stopped working the
        # moment stance was removed. analyzed_at cannot serve either - the
        # column carries DEFAULT now(), so a preview-only row has it set too,
        # which made every cluster look analysed.
        if cached and cached.get("sources_used") is not None:
            print(f"Cached analysis from {cached['analyzed_at']}")
            return cached

    try:
        return _run_deep_analysis(cluster_id)
    except Exception as exc:
        set_status(cluster_id, ANALYSIS_FAILED, f"{type(exc).__name__}: {exc}")
        raise

def _run_deep_analysis(cluster_id):
    started = time.time()
    timings = {}
    cluster, articles = load_cluster(cluster_id)
    if not cluster:
        raise ClusterNotFound(f"Cluster {cluster_id} not found")

    coherence = cluster.get("coherence")
    print(f"Cluster {cluster_id} [{cluster['topic_label']}] - {len(articles)} articles"
          + (f", coherence {coherence:.2f}" if coherence is not None else ""))
    if coherence is not None and coherence < CLUSTER_MIN_COHERENCE:
        print(f"  WARNING: below the {CLUSTER_MIN_COHERENCE} coherence floor - these "
              f"articles are not one story, so every result below is unreliable")

    mark = time.time()
    title_summary = representative_title([a["title"] for a in articles])
    save_preview(cluster_id, title_summary)
    mark_preview_ready(cluster_id)
    timings["title_summary"] = time.time() - mark
    print(f"Preview ({timings['title_summary']:.1f}s): {title_summary}")

    print("Fetching article text (transient)...")
    mark = time.time()
    bodies = fetch_many([a["url"] for a in articles])
    timings["fetch"] = time.time() - mark
    got = sum(1 for b in bodies if b)
    print(f"  retrieved {got}/{len(articles)} in {timings['fetch']:.1f}s")

    mark = time.time()
    claims = []
    for article, body in zip(articles, bodies, strict=True):
        text = body or f"{article['title']} {article['snippet'] or ''}"
        for claim in extract_claims(text):
            claim["source"] = article["source_name"]
            claim["article_id"] = article["id"]
            claim["published_utc"] = article.get("published_utc")
            claims.append(claim)
    timings["claim_extraction"] = time.time() - mark

    print(f"Extracted {len(claims)} candidate claims in {timings['claim_extraction']:.1f}s")

    print("Grouping claims into facts...")
    mark = time.time()
    groups = analyze_cluster_claims(
        claims,
        all_sources=[a["source_name"] for a, b in zip(articles, bodies, strict=True) if b],
        unread_sources=[a["source_name"] for a, b in zip(articles, bodies, strict=True) if not b])
    timings["coverage"] = time.time() - mark
    print(f"  {len(groups)} facts carried by more than one claim")

    mark = time.time()
    digest = build_digest(claims, articles)
    timings["figures"] = time.time() - mark
    tiers = summarise(digest)
    print(f"  figures: {tiers['shared']} shared, {tiers['single']} single-source, "
          f"{tiers['untyped']} untyped")

    print("Scoring how each outlet describes shared entities...")
    mark = time.time()
    framing = analyze_framing(claims)
    timings["framing"] = time.time() - mark
    split = sum(1 for f in framing if f["diverges"])
    print(f"  {len(framing)} entities named by 2+ sources, {split} framed differently")

    subject = derive_subject([article["title"] for article in articles])
    print(f"Subject: {subject}")

    result = {"title_summary": title_summary, "consensus": groups,
              "subject": subject, "framing": framing, "figure_digest": digest}
    save_analysis(cluster_id, result, got)
    set_status(cluster_id, ANALYSIS_DEEP_READY)
    total = time.time() - started

    print(f"\n--- TIMING ({total:.1f}s total) ---")
    for stage, seconds in timings.items():
        print(f"  {stage:<18} {seconds:>7.1f}s  ({seconds/total*100:>4.1f}%)")

    return result

def _as_list(value):
    if isinstance(value, str):
        return json.loads(value)
    return value or []

def print_report(result):
    if result.get("title_summary"):
        print("\n--- PREVIEW (titles only) ---")
        print(result["title_summary"])

    if result.get("subject"):
        print(f"Subject: {result['subject']}")

    groups = _as_list(result.get("consensus"))
    print(f"\n--- COVERAGE ({len(groups)} facts) ---")
    for group in groups:
        print(f"\nFact [{group['anchor'].get('source', '?')}]: {group['anchor']['text'][:150]}")
        reported = group.get("reported_by") or []
        omitted = group.get("omitted_by") or []
        unread = group.get("not_checked") or []
        print(f"  reported by {len(reported)}: {', '.join(reported) or '-'}")
        if omitted:
            print(f"  NOT reported by {len(omitted)}: {', '.join(omitted)}")
        if unread:
            print(f"  could not read: {', '.join(unread)}")
        for member in group["members"]:
            print(f"   - d={member.get('distance', '?')} "
                  f"[{member['claim'].get('source','?')}] {member['claim']['text'][:100]}")

    framing = _as_list(result.get("framing"))
    split = [f for f in framing if f.get("diverges")]
    print(f"\n--- FRAMING ({len(framing)} shared entities, {len(split)} split) ---")
    if not framing:
        print("No entity was named by two or more sources.")
    for record in framing[:6]:
        marker = "  << framed differently" if record.get("diverges") else ""
        print(f"\n{record['entity']}  (spread {record['spread']:+.2f}){marker}")
        for line in describe_framing(record):
            print(f"  {line}")

    digest = _as_list(result.get("figure_digest"))
    groups = digest_groups(digest)
    tiers = summarise(digest)
    print(f"\n--- FIGURES ({tiers['shared']} shared, "
          f"{tiers['single']} single-source, {tiers['untyped']} untyped) ---")

    if not groups:
        print("No two outlets published the same kind of quantity.")
    for group in groups:
        print(f"\n{len(group['sources'])} outlets gave a figure in '{group['unit']}':")
        for row in group["values"]:
            marks = []
            if row["credited_to"]:
                marks.append(f"credits {row['credited_to']}")
            if row["cumulative"]:
                marks.append("running total")
            if row["scope"]:
                marks.append("re: " + ", ".join(row["scope"][:2]))
            note = ("  (" + "; ".join(marks) + ")") if marks else ""
            stamp = (row.get("published") or "")[:10]
            sim = row.get("similarity")
            rank = f"sim {sim:.2f}  " if sim is not None else ""
            print(f"   {rank}{row['figure']:>12}  [{row['source']}]"
                  f"{'  ' + stamp if stamp else ''}{note}")
            if row.get("article_title"):
                print(f"       from: {row['article_title'][:76]}")
            # the surrounding sentences, so the reader sees what the number is
            # attached to - "of those, 300 were minors" reads as a subset
            context = row.get("context") or row["sentence"]
            print(f"       {context[:300]}")
            if row.get("url"):
                print(f"       {row['url']}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python -m backend.analysis.runner <cluster_id> [--refresh] [--preview]"
        )
    cluster = int(sys.argv[1])
    refresh = "--refresh" in sys.argv
    try:
        if "--preview" in sys.argv:
            print(preview_cluster(cluster, refresh=refresh))
        else:
            print_report(analyze_cluster(cluster, refresh=refresh))
    except ClusterNotFound as exc:
        raise SystemExit(str(exc)) from exc
