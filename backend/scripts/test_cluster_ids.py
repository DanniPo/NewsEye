"""Does a story keep its cluster id when the window is re-clustered?

Every clustering run starts from nothing, so continuity has to be recovered by
matching each new cluster to the old one it continues. Get it wrong one way and
story-42.html silently shows a different story; get it wrong the other way and
every re-cluster throws away analyses that were still valid.

Each case gives the stored clusters (id -> articles), the new run's clusters
(label -> articles), and which old id each new label should inherit.

    python -m backend.scripts.test_cluster_ids
"""
import sys

from backend.nlp.clustering import match_clusters

CASES = [
    ("identical run",
     {1: {10, 11, 12}, 2: {20, 21}},
     {0: {10, 11, 12}, 1: {20, 21}},
     {0: 1, 1: 2}),
    ("story grows from 2 to 6 articles",
     {1: {10, 11}},
     {0: {10, 11, 12, 13, 14, 15}},
     {0: 1}),
    ("oldest articles age out of the window",
     {1: {10, 11, 12, 13}},
     {0: {12, 13, 14}},
     {0: 1}),
    ("two-article story swaps one article",
     {1: {10, 11}},
     {0: {10, 12}},
     {0: 1}),
    ("genuinely new story gets no id",
     {1: {10, 11, 12}},
     {0: {10, 11, 12}, 1: {30, 31}},
     {0: 1}),
    ("one stray article is not continuity",
     {1: {10, 11, 12, 13, 14, 15}},
     {0: {15, 30, 31, 32, 33}},
     {}),
    ("split: larger half keeps the id",
     {1: {10, 11, 12, 13, 14, 15, 16}},
     {0: {10, 11}, 1: {12, 13, 14, 15, 16}},
     {1: 1}),
    ("merge: larger story's id survives",
     {1: {10, 11}, 2: {20, 21, 22, 23}},
     {0: {10, 11, 20, 21, 22, 23}},
     {0: 2}),
    ("no id is handed to two clusters",
     {1: {10, 11, 12, 13}},
     {0: {10, 11}, 1: {12, 13}},
     {0: 1}),
    ("empty history",
     {},
     {0: {10, 11}},
     {}),
]


if __name__ == "__main__":
    passed = 0
    for name, previous, current, expected in CASES:
        got = match_clusters(previous, current)
        ok = got == expected
        passed += ok
        detail = "" if ok else f"  expected {expected}, got {got}"
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{detail}")
    print(f"\n{passed}/{len(CASES)} continuity cases")
    sys.exit(0 if passed == len(CASES) else 1)
