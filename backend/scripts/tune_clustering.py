"""Sweep HDBSCAN parameters to find settings that avoid degenerate clustering."""
import sys
from collections import Counter

import hdbscan
import numpy as np

from backend.config import CLUSTER_WINDOW_DAYS, MAX_CLUSTER_SHARE
from backend.nlp.clustering import load_articles, parse_embedding


def summarize(labels):
    counts = Counter(x for x in labels if x != -1)
    noise = int((labels == -1).sum())
    if not counts:
        return 0, noise, 0
    return len(counts), noise, max(counts.values())

def main():
    window = None if "--all" in sys.argv else CLUSTER_WINDOW_DAYS
    rows = load_articles(window)
    X = np.array([parse_embedding(r["embedding"]) for r in rows], dtype=float)
    scope = f"last {window} days" if window else "all time"
    print(f"{len(X)} embeddings ({scope}), dim={X.shape[1]}")
    print(f"Rejecting any cluster above {MAX_CLUSTER_SHARE:.0%} = {int(len(X)*MAX_CLUSTER_SHARE)} articles\n")

    print(f"{'mcs':>4} {'ms':>4} {'eps':>6} {'clusters':>9} {'noise':>7} {'largest':>8}  {'verdict':>10}")
    print("-" * 56)
    best = []
    for mcs in (2, 3, 4, 5, 6):
        for ms in (1, 2, 3):
            for eps in (0.0, 0.1, 0.2):
                cl = hdbscan.HDBSCAN(min_cluster_size=mcs, min_samples=ms,
                                     cluster_selection_epsilon=eps)
                labels = cl.fit_predict(X)
                n, noise, largest = summarize(labels)
                ok = n > 0 and largest <= len(X) * MAX_CLUSTER_SHARE
                verdict = "ok" if ok else "degenerate"
                print(f"{mcs:>4} {ms:>4} {eps:>6.1f} {n:>9} {noise:>7} {largest:>8}  {verdict:>10}")
                if ok:
                    best.append((n, noise, largest, mcs, ms, eps))

    if best:
        best.sort(key=lambda t: (-t[0], t[1]))
        n, noise, largest, mcs, ms, eps = best[0]
        print(f"\nBest: min_cluster_size={mcs}, min_samples={ms}, epsilon={eps}")
        print(f"  {n} clusters, largest {largest}, {noise} noise ({noise/len(X):.0%})")
    else:
        print("\nNo non-degenerate settings found for this window")

if __name__ == "__main__":
    main()
