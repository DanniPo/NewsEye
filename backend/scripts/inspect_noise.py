from collections import defaultdict
from backend.db.connection import get_cursor

def inspect_noise(title_max_len=80, max_per_category=20):
    with get_cursor() as cur:
        cur.execute("""
            SELECT a.id, a.title, a.category
            FROM articles a
            WHERE a.embedding IS NOT NULL
              AND a.id NOT IN (SELECT article_id FROM cluster_members)
            ORDER BY a.category NULLS LAST, a.title
        """)
        rows = cur.fetchall()

    print(f"Total noise articles: {len(rows)}")
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
