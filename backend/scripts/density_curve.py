"""How does cross-source yield scale with corpus size?

The product only works on clusters several outlets covered, and those are 7% of
the corpus. The obvious answer is "ingest more", but how much more is worth it
depends on the shape of the curve - and one before/after data point cannot tell
you whether it is linear, superlinear, or already saturating.

This subsamples the stored corpus at increasing rates, clusters each subsample in
memory, and counts what survives. It never writes to the database.

    python -m backend.scripts.density_curve
"""
import random

import hdbscan
import numpy as np

from backend.config import (
    CLUSTER_MIN_COHERENCE, HDBSCAN_MIN_CLUSTER_SIZE, HDBSCAN_MIN_SAMPLES,
)
from backend.db.connection import get_cursor
from backend.nlp.clustering import cluster_coherence, parse_embedding

FRACTIONS = (0.25, 0.40, 0.55, 0.70, 0.85, 1.00)
TRIALS = 3


def load():
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, source_name, embedding FROM articles
            WHERE embedding IS NOT NULL
        """)
        rows = cur.fetchall()
    vectors = np.array([parse_embedding(r["embedding"]) for r in rows], dtype=float)
    return [r["source_name"] for r in rows], vectors


def measure(sources, vectors):
    labels = hdbscan.HDBSCAN(
        min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
        min_samples=HDBSCAN_MIN_SAMPLES,
    ).fit_predict(vectors)

    groups = {}
    for index, label in enumerate(labels):
        if label != -1:
            groups.setdefault(label, []).append(index)

    usable = three_plus = 0
    for members in groups.values():
        coherence = cluster_coherence(vectors[members])
        distinct = len({sources[i] for i in members})
        if coherence >= CLUSTER_MIN_COHERENCE and distinct >= 2:
            usable += 1
            if distinct >= 3:
                three_plus += 1
    return len(groups), usable, three_plus


def main():
    sources, vectors = load()
    total = len(sources)
    print(f"corpus: {total} articles, {len(set(sources))} sources")
    print(f"averaging {TRIALS} random subsamples per point" + "\n")
    print(f"{'articles':>9}{'share':>8}{'clusters':>10}{'usable':>9}{'3+ src':>8}"
          f"{'3+ per 100 art':>16}")

    rng = random.Random(20260917)
    baseline = None
    for fraction in FRACTIONS:
        n = max(int(total * fraction), HDBSCAN_MIN_CLUSTER_SIZE + 1)
        runs = []
        for trial in range(TRIALS if fraction < 1.0 else 1):
            picks = rng.sample(range(total), n)
            runs.append(measure([sources[i] for i in picks], vectors[picks]))
        clusters = sum(r[0] for r in runs) / len(runs)
        usable = sum(r[1] for r in runs) / len(runs)
        three = sum(r[2] for r in runs) / len(runs)
        density = three / n * 100
        if baseline is None:
            baseline = (n, three)
        print(f"{n:>9}{fraction:>8.0%}{clusters:>10.0f}{usable:>9.1f}{three:>8.1f}"
              f"{density:>16.2f}")

    # elasticity: a doubling of the corpus multiplies 3+ source clusters by how much?
    n0, t0 = baseline
    n1 = total
    t1 = measure(sources, vectors)[2]
    if t0 > 0 and n1 > n0:
        exponent = np.log(t1 / t0) / np.log(n1 / n0)
        print(f"\nfitted exponent over the sampled range: {exponent:.2f}")
        print(f"  (1.0 = linear; above 1.0 = each extra article is worth more than the last)")
        print(f"  a doubling of the corpus implies x{2 ** exponent:.1f} three-source clusters")


if __name__ == "__main__":
    main()
