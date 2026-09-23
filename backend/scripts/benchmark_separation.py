"""Measure embedding separation - the property that makes clustering stable."""
import hdbscan
import numpy as np
from collections import Counter
from backend.config import CLUSTER_WINDOW_DAYS, MAX_CLUSTER_SHARE
from backend.nlp.clustering import load_articles, parse_embedding

def separation_stats(X):
    sims = X @ X.T
    np.fill_diagonal(sims, -np.inf)
    ordered = np.sort(sims, axis=1)[:, ::-1]
    nn1 = np.sqrt(np.maximum(2 - 2 * ordered[:, 0], 0))
    nn2 = np.sqrt(np.maximum(2 - 2 * ordered[:, 1], 0))
    return nn1, nn2

def stability(X, mcs=2, ms=1):
    # fraction of subsamples that avoid a degenerate mega-cluster
    ok = 0
    trials = 5
    rng = np.random.default_rng(0)
    for _ in range(trials):
        idx = rng.choice(len(X), size=int(len(X) * 0.9), replace=False)
        labels = hdbscan.HDBSCAN(min_cluster_size=mcs, min_samples=ms).fit_predict(X[idx])
        counts = Counter(l for l in labels if l != -1)
        largest = max(counts.values()) if counts else 0
        if counts and largest <= len(idx) * MAX_CLUSTER_SHARE:
            ok += 1
    return ok / trials

def main():
    rows = load_articles(CLUSTER_WINDOW_DAYS)
    X = np.array([parse_embedding(r["embedding"]) for r in rows], dtype=float)
    nn1, nn2 = separation_stats(X)

    print(f"Articles in window: {len(X)}")
    print(f"1st-NN distance: mean={nn1.mean():.4f} median={np.median(nn1):.4f} min={nn1.min():.4f}")
    print(f"2nd-NN distance: mean={nn2.mean():.4f} median={np.median(nn2):.4f}")
    print(f"Spread (p90-p10): {np.percentile(nn2,90)-np.percentile(nn2,10):.4f}")

    labels = hdbscan.HDBSCAN(min_cluster_size=2, min_samples=1).fit_predict(X)
    counts = Counter(l for l in labels if l != -1)
    largest = max(counts.values()) if counts else 0
    print(f"\nClusters: {len(counts)} | largest: {largest} "
          f"({largest/len(X):.0%}) | noise: {int((labels==-1).sum())}")
    print(f"Stability across 90% subsamples: {stability(X):.0%}")

if __name__ == "__main__":
    main()
