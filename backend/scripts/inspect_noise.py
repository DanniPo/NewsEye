"""List the articles HDBSCAN left out of every cluster, grouped by topic.

Only the clustering window counts. Articles older than it are never clustered
at all, so counting them as noise reported 3,928 "noise" articles when the
window held ~1,800 and HDBSCAN had left out ~830 of those.

    python -m backend.scripts.inspect_noise
"""
from collections import defaultdict

from backend.config import CLUSTER_WINDOW_DAYS
from backend.db.connection import get_cursor


def inspect_noise(title_max_len=80, max_per_category=20, window_days=CLUSTER_WINDOW_DAYS):
    with get_cursor() as cur:
        cur.execute("""
            SELECT count(*) AS n FROM articles
            WHERE embedding IS NOT NULL
              AND published_utc >= now() - %s::interval
        """, (f"{window_days} days",))
        in_window = cur.fetchone()["n"]
        cur.execute("""
            SELECT a.id, a.title, a.category
            FROM articles a
            WHERE a.embedding IS NOT NULL
              AND a.published_utc >= now() - %s::interval
              AND NOT EXISTS (SELECT 1 FROM cluster_members cm WHERE cm.article_id = a.id)
            ORDER BY a.category NULLS LAST, a.title
        """, (f"{window_days} days",))
        rows = cur.fetchall()

    share = len(rows) / in_window if in_window else 0
    print(f"Noise: {len(rows)} of {in_window} articles in the last {window_days} days "
          f"({share:.0%})")
    grouped = defaultdict(list)
    for r in rows:
        grouped[r["category"] or "Uncategorized"].append(r["title"])

    for category, titles in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        print(f"--- {category} ({len(titles)}) ---")
        for t in titles[:max_per_category]:
            print(" -", t[:title_max_len])
        if len(titles) > max_per_category:
            print(f"   ... and {len(titles) - max_per_category} more")

if __name__ == "__main__":
    inspect_noise()
