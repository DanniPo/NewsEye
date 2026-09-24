"""Interactive cluster review: step through clusters and record your own verdict."""
import csv
import os
from collections import defaultdict

from backend.db.connection import get_cursor

OUTPUT_PATH = "cluster_review.csv"

def load_clusters():
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.id AS cluster_id, c.topic_label, c.article_count,
                   a.title, a.source_name, a.category
            FROM clusters c
            JOIN cluster_members cm ON cm.cluster_id = c.id
            JOIN articles a ON a.id = cm.article_id
            ORDER BY c.article_count DESC, c.id, a.title
        """)
        rows = cur.fetchall()

    clusters = defaultdict(lambda: {"label": None, "articles": []})
    for r in rows:
        c = clusters[r["cluster_id"]]
        c["label"] = r["topic_label"]
        c["articles"].append((r["title"], r["source_name"], r["category"]))
    return clusters

def already_reviewed():
    if not os.path.exists(OUTPUT_PATH):
        return set()
    with open(OUTPUT_PATH, newline="", encoding="utf-8") as f:
        return {int(row["cluster_id"]) for row in csv.DictReader(row for row in f)}

def review():
    clusters = load_clusters()
    done = already_reviewed()
    pending = [(cid, c) for cid, c in clusters.items() if cid not in done]

    if not pending:
        print(f"All {len(clusters)} clusters already reviewed in {OUTPUT_PATH}")
        return

    print(f"{len(pending)} clusters to review ({len(done)} already done)")
    print("For each cluster: [c]oherent  [m]ixed  [b]ad  [l]abel-wrong  [s]kip  [q]uit\n")

    new_file = not os.path.exists(OUTPUT_PATH)
    with open(OUTPUT_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["cluster_id", "assigned_label", "article_count", "verdict", "notes"])

        for cid, c in pending:
            print("=" * 78)
            print(f"Cluster {cid} | label: {c['label']} | {len(c['articles'])} articles")
            print("=" * 78)
            for title, source, _category in c["articles"]:
                print(f"  [{(source or '?')[:18]:<18}] {title[:70]}")

            verdict = input("\nVerdict (c/m/b/l/s/q): ").strip().lower()
            if verdict == "q":
                break
            if verdict == "s":
                continue
            notes = input("Notes (optional): ").strip()
            writer.writerow([cid, c["label"], len(c["articles"]), verdict, notes])
            f.flush()
            print()

    print(f"\nSaved to {OUTPUT_PATH}")

def summarize():
    if not os.path.exists(OUTPUT_PATH):
        print(f"No {OUTPUT_PATH} yet - run review first")
        return
    with open(OUTPUT_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    names = {"c": "coherent", "m": "mixed", "b": "bad", "l": "label wrong"}
    counts = defaultdict(int)
    for r in rows:
        counts[r["verdict"]] += 1

    print(f"Reviewed {len(rows)} clusters:")
    for verdict, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {names.get(verdict, verdict):<12} {count:>3}  ({count/len(rows)*100:.0f}%)")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        summarize()
    else:
        review()
