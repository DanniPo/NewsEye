"""Passive-tier summaries: a brief line for every cluster, generated in bulk.

The passive tier is meant to stand on its own - a reader browsing the site sees
story clusters each carrying a one-line summary, before selecting anything. That
only works if the summaries already exist.

They did not. preview_cluster() ran on demand, and re-clustering truncates
cluster_analysis, so every rebuild left 149 clusters with no summary until
somebody opened one. This generates the missing ones in a single pass over the
summarisation model, which is far cheaper than loading it per request.

    python -m backend.nlp.previews          # fill in what is missing
    python -m backend.nlp.previews --all    # regenerate everything
"""
import argparse
import time

from backend.config import ANALYSIS_PREVIEW_READY, TITLE_SUMMARY_MODEL
from backend.db.connection import get_cursor


def clusters_needing_preview(regenerate=False):
    query = """
        SELECT c.id, c.topic_label, c.coherence,
               array_agg(a.title ORDER BY a.published_utc DESC NULLS LAST) AS titles
        FROM clusters c
        JOIN cluster_members cm ON cm.cluster_id = c.id
        JOIN articles a ON a.id = cm.article_id
        LEFT JOIN cluster_analysis ca ON ca.cluster_id = c.id
        {where}
        GROUP BY c.id, c.topic_label, c.coherence
        ORDER BY c.article_count DESC
    """.format(where="" if regenerate else "WHERE ca.title_summary IS NULL")
    with get_cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def save_previews(rows):
    """One transaction for the batch: a half-written passive tier helps nobody."""
    with get_cursor() as cur:
        for cluster_id, summary in rows:
            cur.execute("""
                INSERT INTO cluster_analysis
                    (cluster_id, title_summary, title_summary_at, summary_model)
                VALUES (%s, %s, now(), %s)
                ON CONFLICT (cluster_id) DO UPDATE SET
                    title_summary = EXCLUDED.title_summary,
                    title_summary_at = now(),
                    summary_model = EXCLUDED.summary_model
            """, (cluster_id, summary, TITLE_SUMMARY_MODEL))
            cur.execute(
                "UPDATE clusters SET analysis_status = %s "
                "WHERE id = %s AND analysis_status = 'pending'",
                (ANALYSIS_PREVIEW_READY, cluster_id)
            )


def generate_previews(regenerate=False, limit=None):
    from backend.analysis.story import representative_title

    pending = clusters_needing_preview(regenerate)
    if limit:
        pending = pending[:limit]
    if not pending:
        print("Every cluster already has a summary")
        return 0

    print(f"Summarising {len(pending)} clusters...")
    started = time.time()
    done = []
    for index, row in enumerate(pending, start=1):
        try:
            summary = representative_title(row["titles"])
        except Exception as exc:
            print(f"  [{index}/{len(pending)}] cluster {row['id']} failed: "
                  f"{type(exc).__name__}: {exc}")
            continue
        done.append((row["id"], summary))
        if index % 25 == 0 or index == len(pending):
            print(f"  [{index}/{len(pending)}] {time.time() - started:.0f}s elapsed")

    save_previews(done)
    elapsed = time.time() - started
    print(f"Wrote {len(done)} summaries in {elapsed:.1f}s "
          f"({elapsed / max(len(done), 1):.2f}s each)")
    return len(done)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true",
                        help="regenerate summaries that already exist")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    generate_previews(regenerate=args.all, limit=args.limit or None)
