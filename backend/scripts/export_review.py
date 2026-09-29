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

from backend.analysis.runner import ClusterNotFound, analyze_cluster
from backend.db.connection import get_cursor

DEFAULT_OUTPUT = "review_export.json"
# what a story page reads, and nothing else
EXPORTED = ("topic_label", "coherence", "retrieved", "title_summary", "subject",
            "articles", "consensus", "framing", "figure_digest")


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
    """One cluster's page data, from the same deep pass the active tier runs.

    This used to repeat the pipeline step by step - fetch, claims, coverage,
    framing, digest - beside runner._run_deep_analysis, so any change to one
    silently diverged the site from the database. It now calls the runner and
    only reshapes the result.

    Always a fresh run, never the cache: the site marks outlets "could not
    read", and which articles were readable is known only during a run.
    """
    try:
        result = analyze_cluster(cluster_id, refresh=True)
    except ClusterNotFound:
        print(f"  cluster {cluster_id} not found, skipping")
        return None
    return {"cluster_id": cluster_id, **{key: result[key] for key in EXPORTED}}


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
