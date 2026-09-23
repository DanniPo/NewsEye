import sys
import time
from backend.config import ZERO_SHOT_MODEL
from backend.db.connection import get_cursor
from backend.nlp.classification import classify_topics_batch

BATCH_SIZE = 16

def backfill_categories(reclassify_all=False):
    query = "SELECT id, title FROM articles"
    if not reclassify_all:
        query += " WHERE category IS NULL"
    with get_cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

    scope = "all" if reclassify_all else "uncategorized"
    print(f"Classifying {len(rows)} {scope} articles...")
    start_time = time.time()
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        results = classify_topics_batch([r["title"] for r in batch])
        with get_cursor() as cur:
            for r, (category, _) in zip(batch, results):
                cur.execute("UPDATE articles SET category = %s, category_model = %s WHERE id = %s",
                            (category, ZERO_SHOT_MODEL, r["id"]))
        done = min(start + BATCH_SIZE, len(rows))
        elapsed = time.time() - start_time
        print(f"  {done}/{len(rows)} ({elapsed:.0f}s elapsed, {elapsed/done*1000:.0f} ms/article)")

    total = time.time() - start_time
    print(f"Done in {total:.1f}s ({total/max(len(rows),1)*1000:.0f} ms/article)")

if __name__ == "__main__":
    backfill_categories(reclassify_all="--all" in sys.argv)
