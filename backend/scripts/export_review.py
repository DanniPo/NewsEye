"""Run the deep analysis over the richest clusters and export it for the site.

Writes the JSON bundle build_site.py turns into the static pages. Each cluster
carries what its story page shows - headlines and links, the coverage table, the
framing quotes and the figure digest - and nothing else. The same results are
saved to cluster_analysis as they are produced.

    python -m backend.scripts.export_review --top 14
    python -m backend.scripts.export_review 5 32 1
"""
import argparse
import json
import time

from backend.analysis.claims import extract_claims
from backend.analysis.consensus import analyze_cluster_claims
from backend.analysis.digest import build_digest
from backend.analysis.framing import analyze_framing
from backend.analysis.runner import load_cluster, save_analysis, set_status
from backend.analysis.story import representative_title
from backend.analysis.subject import derive_subject
from backend.config import ANALYSIS_DEEP_READY
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
    subject = derive_subject(titles)

    result = {"title_summary": title_summary, "consensus": groups,
              "framing": framing, "figure_digest": digest, "subject": subject}
    retrieved = sum(1 for b in bodies if b)
    save_analysis(cluster_id, result, retrieved)
    set_status(cluster_id, ANALYSIS_DEEP_READY)
    print(f"  done in {time.time() - started:.1f}s ({retrieved}/{len(articles)} fetched, "
          f"{len(claims)} claims, {len(digest)} figures)")

    return {
        "cluster_id": cluster_id,
        "topic_label": cluster["topic_label"],
        "coherence": cluster.get("coherence"),
        "retrieved": retrieved,
        "title_summary": title_summary,
        "subject": subject,
        "articles": [
            {"source": a["source_name"], "title": a["title"], "url": a["url"],
             "fetched": bool(b)}
            for a, b in zip(articles, bodies, strict=True)
        ],
        "consensus": groups,
        "framing": framing,
        "figure_digest": digest,
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

    bundle = {"generated_at": time.strftime("%Y-%m-%d %H:%M"), "clusters": []}

    for index, cluster_id in enumerate(ids, start=1):
        print(f"[{index}/{len(ids)}] cluster {cluster_id}...", flush=True)
        try:
            entry = analyse(cluster_id)
        except Exception as exc:
            print(f"  failed: {type(exc).__name__}: {exc}")
            continue
        if entry:
            bundle["clusters"].append(entry)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=1, default=str)
    print(f"\nWrote {args.out} ({len(bundle['clusters'])} clusters)")


if __name__ == "__main__":
    main()
