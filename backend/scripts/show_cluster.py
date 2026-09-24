"""Print the source articles of one cluster for manual review."""
import sys

from backend.db.connection import get_cursor


def show(cluster_id):
    with get_cursor() as cur:
        cur.execute("SELECT topic_label, article_count FROM clusters WHERE id = %s", (cluster_id,))
        cluster = cur.fetchone()
        if not cluster:
            print(f"Cluster {cluster_id} not found")
            return
        print(f"Cluster {cluster_id} [{cluster['topic_label']}] - {cluster['article_count']} articles\n")

        cur.execute("""
            SELECT a.source_name, a.title, a.category, a.url
            FROM cluster_members cm
            JOIN articles a ON a.id = cm.article_id
            WHERE cm.cluster_id = %s
            ORDER BY a.source_name
        """, (cluster_id,))
        for r in cur.fetchall():
            source = (r["source_name"] or "?")[:18]
            print(f"[{source:<18}] ({r['category']}) {r['title'][:80]}")

if __name__ == "__main__":
    show(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
