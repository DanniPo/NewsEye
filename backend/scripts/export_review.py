"""Export active-tier analysis for manual evaluation.

Runs the deep pipeline over several clusters and writes one JSON bundle holding
the intermediates the runner throws away: the exact text stance saw, every parsed
figure (not only the ones flagged as conflicts, so misses are visible too), and
NLI distances per pair. Optionally re-runs stance over full bodies as well, which
is the A/B behind the title+lead cap.

    python -m backend.scripts.export_review --top 8 --ab
    python -m backend.scripts.export_review 5 32 1

Article leads are quoted in the output because stance cannot be judged without
them. This bundle is an evaluation artefact, not the production store - the
pipeline itself still keeps nothing but derived results.
"""
import argparse
import json
import time

from backend.analysis.claims import extract_claims
from backend.analysis.consensus import MATCH_SIMILARITY, analyze_cluster_claims
from backend.analysis.digest import build_digest
from backend.analysis.figures import (
    cluster_vocabulary,
    parse_figures,
)
from backend.analysis.framing import analyze_framing
from backend.analysis.runner import load_cluster, save_analysis, set_status
from backend.analysis.story import representative_title
from backend.analysis.subject import derive_subject
from backend.config import (
    ANALYSIS_DEEP_READY,
    CLAIM_MATCH_MAX_DISTANCE,
    SENTIMENT_MODEL,
    TITLE_SUMMARY_MODEL,
)
from backend.db.connection import get_cursor

DEFAULT_OUTPUT = "review_export.json"


def multi_source_clusters(limit):
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.id
            FROM clusters c
            JOIN cluster_members cm ON cm.cluster_id = c.id
            JOIN articles a ON a.id = cm.article_id
            GROUP BY c.id, c.article_count
            HAVING count(DISTINCT a.source_name) >= 2
            ORDER BY count(DISTINCT a.source_name) DESC, c.article_count DESC
            LIMIT %s
        """, (limit,))
        return [r["id"] for r in cur.fetchall()]


def all_figures(claims):
    """Every parsed figure with the unit and subject that decided its placement."""
    ubiquitous = cluster_vocabulary(claims)
    rows = []
    for claim in claims:
        for figure in parse_figures(claim["text"]):
            tokens = figure["subject"]["tokens"] - ubiquitous
            rows.append({
                "source": claim.get("source"),
                "figure": figure["text"],
                "value": figure["value"],
                "unit": figure["unit"],
                "state": figure["state"],
                "subject": sorted(tokens),
                "dropped_as_cluster_vocab": sorted(figure["subject"]["tokens"] & ubiquitous),
                "typed": bool(figure["unit"]),
                "claim": claim["text"],
            })
    return rows, sorted(ubiquitous)


def analyse(cluster_id):
    from backend.ingestion.fetch import fetch_many

    cluster, articles = load_cluster(cluster_id)
    if not cluster:
        print(f"  cluster {cluster_id} not found, skipping")
        return None

    started = time.time()
    titles = [a["title"] for a in articles]
    title_summary = representative_title(titles)
    bodies = fetch_many([a["url"] for a in articles])

    claims = []
    for article, body in zip(articles, bodies, strict=True):
        text = body or f"{article['title']} {article['snippet'] or ''}"
        for claim in extract_claims(text):
            claim["source"] = article["source_name"]
            claim["article_id"] = article["id"]
            claim["published_utc"] = article.get("published_utc")
            claims.append(claim)

    groups = analyze_cluster_claims(
        claims,
        all_sources=[a["source_name"] for a, b in zip(articles, bodies, strict=True) if b],
        unread_sources=[a["source_name"] for a, b in zip(articles, bodies, strict=True) if not b])
    framing = analyze_framing(claims)
    digest = build_digest(claims, articles)
    figures, ubiquitous = all_figures(claims)
    subject = derive_subject(titles)

    result = {"title_summary": title_summary, "consensus": groups,
              "framing": framing, "figure_digest": digest, "subject": subject}
    retrieved = sum(1 for b in bodies if b)
    save_analysis(cluster_id, result, retrieved)
    set_status(cluster_id, ANALYSIS_DEEP_READY)

    return {
        "cluster_id": cluster_id,
        "topic_label": cluster["topic_label"],
        "article_count": cluster["article_count"],
        "coherence": cluster.get("coherence"),
        "retrieved": retrieved,
        "seconds": round(time.time() - started, 1),
        "title_summary": title_summary,
        "subject": subject,
        "articles": [
            {
                "article_id": a["id"],
                "source": a["source_name"],
                "title": a["title"],
                "url": a["url"],
                "fetched": bool(b),
                "body_chars": len(b or ""),
            }
            for a, b in zip(articles, bodies, strict=True)
        ],
        "consensus": groups,
        "framing": framing,
        "figure_digest": digest,
        "figures": figures,
        "cluster_vocabulary": ubiquitous,
        "claim_count": len(claims),
        # every claim, not just the ones carrying a figure: cluster_vocabulary is
        # measured over all of them, so a recheck needs the same input to agree
        "claims": [{"text": c["text"], "source": c.get("source")} for c in claims],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("clusters", nargs="*", type=int)
    parser.add_argument("--top", type=int, default=0,
                        help="take the N most source-diverse multi-source clusters")
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    ids = args.clusters or multi_source_clusters(args.top or 8)
    print(f"Analysing {len(ids)} clusters: {ids}")

    bundle = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "config": {
            "claim_match_max_distance": CLAIM_MATCH_MAX_DISTANCE,
            "claim_match_min_similarity": round(MATCH_SIMILARITY, 3),
            "summary_model": TITLE_SUMMARY_MODEL,
            "sentiment_model": SENTIMENT_MODEL,
        },
        "clusters": [],
    }

    for index, cluster_id in enumerate(ids, start=1):
        print(f"[{index}/{len(ids)}] cluster {cluster_id}...", flush=True)
        try:
            entry = analyse(cluster_id)
        except Exception as exc:
            print(f"  failed: {type(exc).__name__}: {exc}")
            continue
        if entry:
            bundle["clusters"].append(entry)
            print(f"  done in {entry['seconds']}s "
                  f"({entry['retrieved']}/{len(entry['articles'])} fetched, "
                  f"{entry['claim_count']} claims, "
                  f"{len(entry['figure_digest'])} figures)")

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=1, default=str)
    print(f"\nWrote {args.out} ({len(bundle['clusters'])} clusters)")


if __name__ == "__main__":
    main()
