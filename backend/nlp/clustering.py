import time
from collections import Counter, defaultdict

import hdbscan
import numpy as np

from backend.config import (
    ANALYSIS_PENDING,
    CLUSTER_CONTINUITY_SHARE,
    CLUSTER_MIN_COHERENCE,
    CLUSTER_WINDOW_DAYS,
    FALLBACK_LABEL,
    HDBSCAN_MIN_CLUSTER_SIZE,
    HDBSCAN_MIN_SAMPLES,
    MAX_CLUSTER_SHARE,
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
    for article_id, label in zip(article_ids, labels, strict=True):
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
    counts = save_clusters(cluster_map, titles, categories, coherences)
    print(f"  {counts['unchanged']} carried over unchanged (analysis kept), "
          f"{counts['changed']} carried over with new members, "
          f"{counts['new']} new, {counts['ended']} ended")
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


def match_clusters(previous, current, min_share=CLUSTER_CONTINUITY_SHARE):
    """Which previous cluster, if any, each new cluster continues.

    previous maps stored cluster id -> set of article ids; current maps HDBSCAN
    label -> set of article ids. Returns {label: previous cluster id}.

    Every run re-clusters the whole window from scratch, and used to hand out ids
    from 1 again. A story page linked as story-42.html then showed a different
    story after the next run, and every deep analysis was thrown away even when
    the cluster came back article for article.

    A new cluster continues an old one when they share at least min_share of the
    smaller of the two. The smaller side is deliberate: a story that grows from 2
    articles to 6 shares only a third of its new membership, and one that loses
    its oldest articles off the end of the window shares only part of its old
    one, and both are still the same story. Pairs are claimed greedily, most
    shared articles first, so when a story splits the larger half keeps the id
    and when two merge the larger one's id survives.
    """
    owners = defaultdict(set)
    for cluster_id, members in previous.items():
        for article_id in members:
            owners[article_id].add(cluster_id)

    pairs = []
    for label, members in current.items():
        candidates = set().union(*(owners[a] for a in members if a in owners))
        for cluster_id in candidates:
            old = previous[cluster_id]
            shared = len(members & old)
            if shared >= min_share * min(len(members), len(old)):
                overlap = shared / len(members | old)
                pairs.append((-shared, -overlap, cluster_id, label))
    pairs.sort()

    matched, taken = {}, set()
    for _, _, cluster_id, label in pairs:
        if label in matched or cluster_id in taken:
            continue
        matched[label] = cluster_id
        taken.add(cluster_id)
    return matched


def _insert_members(cur, cluster_id, members):
    for article_id in members:
        cur.execute(
            "INSERT INTO cluster_members (cluster_id, article_id) VALUES (%s, %s)",
            (cluster_id, article_id)
        )


def save_clusters(cluster_map, titles, categories, coherences=None):
    """Write a clustering run, keeping the ids of clusters that carried over.

    Returns how many clusters were carried over unchanged, carried over with
    different members, created, and ended.
    """
    # label everything before touching the live tables so a failure leaves them intact
    coherences = coherences or {}
    staged = [(label, label_cluster(members, titles, categories), members,
               coherences.get(label))
              for label, members in cluster_map.items()]

    counts = Counter()
    with get_cursor() as cur:
        cur.execute("SELECT cluster_id, article_id FROM cluster_members")
        previous = defaultdict(set)
        for row in cur.fetchall():
            previous[row["cluster_id"]].add(row["article_id"])
        continued = match_clusters(
            previous, {label: set(members) for label, members in cluster_map.items()})

        # the cascade takes their members and analysis with them
        ended = set(previous) - set(continued.values())
        if ended:
            cur.execute("DELETE FROM clusters WHERE id = ANY(%s)", (sorted(ended),))
        counts["ended"] = len(ended)

        for label, topic_label, members, coherence in staged:
            cluster_id = continued.get(label)
            if cluster_id is None:
                cur.execute(
                    "INSERT INTO clusters (topic_label, article_count, coherence) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (topic_label, len(members), coherence)
                )
                _insert_members(cur, cur.fetchone()["id"], members)
                counts["new"] += 1
                continue

            cur.execute(
                "UPDATE clusters SET topic_label = %s, article_count = %s, "
                "coherence = %s, clustered_at = now() WHERE id = %s",
                (topic_label, len(members), coherence, cluster_id)
            )
            if set(members) == previous[cluster_id]:
                counts["unchanged"] += 1
                continue

            # The analysis describes the old membership. Keeping it would show a
            # coverage table that leaves out an outlet which is now in the story.
            cur.execute("DELETE FROM cluster_members WHERE cluster_id = %s", (cluster_id,))
            _insert_members(cur, cluster_id, members)
            cur.execute("DELETE FROM cluster_analysis WHERE cluster_id = %s", (cluster_id,))
            cur.execute(
                "UPDATE clusters SET analysis_status = %s, analysis_error = NULL "
                "WHERE id = %s", (ANALYSIS_PENDING, cluster_id)
            )
            counts["changed"] += 1
    return counts

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
        raise SystemExit(f"Clustering rejected: {exc}") from exc

    # the passive tier is clusters *and* their summaries: rebuilding the clusters
    # without refilling the summaries leaves the browse view blank until somebody
    # opens a story, which defeats the point of a passive tier
    from backend.nlp.previews import generate_previews
    generate_previews()