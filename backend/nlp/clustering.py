import time
import hdbscan
import numpy as np
from collections import defaultdict, Counter
from backend.config import (
    CLUSTER_MIN_COHERENCE,
    HDBSCAN_MIN_CLUSTER_SIZE,
    HDBSCAN_MIN_SAMPLES,
    CLUSTER_WINDOW_DAYS,
    MAX_CLUSTER_SHARE,
    FALLBACK_LABEL,
)
from backend.db.connection import get_cursor
from backend.nlp.classification import classify_topics_batch

LABEL_SAMPLE_SIZE = 10

class DegenerateClustering(Exception):
    """Raised when one cluster absorbs an implausible share of the corpus."""

def parse_embedding(value):
    # psycopg2 returns pgvector columns as strings like "[0.1,0.2,...]"
    if isinstance(value, str):
        return [float(x) for x in value.strip("[]").split(",")]
    return value

def load_articles(window_days):
    query = "SELECT id, title, category, embedding FROM articles WHERE embedding IS NOT NULL"
    params = ()
    if window_days:
        query += " AND published_utc >= now() - %s::interval"
        params = (f"{window_days} days",)
    with get_cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()

def run_clustering(min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
                   min_samples=HDBSCAN_MIN_SAMPLES,
                   window_days=CLUSTER_WINDOW_DAYS):
    started = time.time()
    scope = f"last {window_days} days" if window_days else "all time"
    print(f"Loading article embeddings ({scope})...")
    rows = load_articles(window_days)

    if len(rows) < min_cluster_size:
        print(f"Only {len(rows)} articles in window - nothing to cluster")
        return 0, len(rows)

    print(f"Loaded {len(rows)} articles with embeddings")
    article_ids = [r["id"] for r in rows]
    titles = {r["id"]: r["title"] for r in rows}
    categories = {r["id"]: r["category"] for r in rows}
    embeddings = np.array([parse_embedding(r["embedding"]) for r in rows], dtype=float)

    print(f"Running HDBSCAN (min_cluster_size={min_cluster_size}, min_samples={min_samples})...")
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples)
    labels = clusterer.fit_predict(embeddings)

    cluster_map = defaultdict(list)
    for article_id, label in zip(article_ids, labels):
        if label != -1:
            cluster_map[label].append(article_id)

    if cluster_map:
        largest = max(len(m) for m in cluster_map.values())
        share = largest / len(rows)
        if share > MAX_CLUSTER_SHARE:
            raise DegenerateClustering(
                f"largest cluster holds {largest}/{len(rows)} articles ({share:.0%}), "
                f"above the {MAX_CLUSTER_SHARE:.0%} limit - existing clusters left untouched"
            )

    index_of = {article_id: i for i, article_id in enumerate(article_ids)}
    coherences = {
        label: cluster_coherence(embeddings[[index_of[a] for a in members]])
        for label, members in cluster_map.items()
    }
    loose = sum(1 for c in coherences.values() if c < CLUSTER_MIN_COHERENCE)

    print(f"Labeling and saving {len(cluster_map)} clusters...")
    save_clusters(cluster_map, titles, categories, coherences)
    print(f"  {loose}/{len(coherences)} below the {CLUSTER_MIN_COHERENCE} coherence "
          f"floor - those are grab-bags, not stories")

    print(f"Completed in {time.time() - started:.1f}s")
    return len(cluster_map), int((labels == -1).sum())

def cluster_coherence(vectors):
    """Mean pairwise cosine similarity among a cluster's members.

    HDBSCAN will happily group articles that merely share a city name. This is the
    cheap check on whether the members are actually one story, and it is stored so
    downstream stages can refuse to speak confidently about a loose cluster.
    """
    if len(vectors) < 2:
        return 1.0
    unit = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    similarity = unit @ unit.T
    n = len(unit)
    return float((similarity.sum() - n) / (n * (n - 1)))


def save_clusters(cluster_map, titles, categories, coherences=None):
    # label everything before touching the live tables so a failure leaves them intact
    coherences = coherences or {}
    staged = [(label_cluster(members, titles, categories), members,
               coherences.get(label))
              for label, members in cluster_map.items()]

    with get_cursor() as cur:
        cur.execute("TRUNCATE clusters, cluster_members RESTART IDENTITY CASCADE")
        for topic_label, members, coherence in staged:
            cur.execute(
                "INSERT INTO clusters (topic_label, article_count, coherence) "
                "VALUES (%s, %s, %s) RETURNING id",
                (topic_label, len(members), coherence)
            )
            cluster_id = cur.fetchone()["id"]
            for article_id in members:
                cur.execute(
                    "INSERT INTO cluster_members (cluster_id, article_id) VALUES (%s, %s)",
                    (cluster_id, article_id)
                )

def label_cluster(member_ids, titles, categories):
    """Majority topic across a sample of the cluster's members.

    Every stored category is trusted, including the fallback. Treating
    FALLBACK_LABEL as "not yet classified" sent 609 of 1085 articles back
    through the zero-shot model on every clustering run - the same model that
    had already looked at the same title at ingest and answered "General". It
    answered "General" again, for about 45 of the stage's 47 seconds.

    Only a genuinely missing category is worth a forward pass.
    """
    votes = Counter()
    unclassified = []
    for article_id in member_ids[:LABEL_SAMPLE_SIZE]:
        category = categories.get(article_id)
        if category:
            votes[category] += 1
        else:
            unclassified.append(article_id)

    if unclassified:
        results = classify_topics_batch([titles[i] for i in unclassified])
        votes.update(category for category, _ in results)

    # a cluster of otherwise-unlabelled articles still gets a name
    if not votes:
        return FALLBACK_LABEL
    # prefer a real topic over the fallback when the cluster carries both
    specific = [(c, n) for c, n in votes.items() if c != FALLBACK_LABEL]
    if specific:
        return max(specific, key=lambda item: item[1])[0]
    return FALLBACK_LABEL

if __name__ == "__main__":
    try:
        n_clusters, n_noise = run_clustering()
        print(f"Found {n_clusters} clusters, {n_noise} noise points")
    except DegenerateClustering as exc:
        raise SystemExit(f"Clustering rejected: {exc}")

    # the passive tier is clusters *and* their summaries: rebuilding the clusters
    # without refilling the summaries leaves the browse view blank until somebody
    # opens a story, which defeats the point of a passive tier
    from backend.nlp.previews import generate_previews
    generate_previews()