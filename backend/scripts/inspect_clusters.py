from itertools import groupby
from backend.db.connection import get_cursor

def inspect_clusters(title_max_len=80):
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.id AS cluster_id, c.topic_label, c.article_count, a.title
            FROM clusters c
            JOIN cluster_members cm ON cm.cluster_id = c.id
            JOIN articles a ON a.id = cm.article_id
            ORDER BY c.article_count DESC, c.id, a.title
        """)
        rows = cur.fetchall()

    for (cluster_id, topic_label, article_count), group in groupby(
        rows, key=lambda r: (r["cluster_id"], r["topic_label"], r["article_count"])
    ):
        print(f"--- Cluster {cluster_id} [{topic_label}] ({article_count} articles) ---")
        for r in group:
            print(" -", r["title"][:title_max_len])

if __name__ == "__main__":
    inspect_clusters()
