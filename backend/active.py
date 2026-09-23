"""Pre-compute the active tier for every cluster worth analysing.

The active tier cannot run inside a web request. Analysing one cluster takes
3-21 seconds depending on how many articles must be fetched, and a fresh process
spends another 30 seconds loading models before it does anything. Nobody waits
that long for a page.

It does not need to. Reading a finished analysis back from the cache takes about
45 milliseconds, so the fix is to make sure the analysis already exists: run this
after the passive tier, in one process, with the models loaded once.

    python -m backend.active                  # analyse everything not yet done
    python -m backend.active --refresh        # redo clusters already analysed
    python -m backend.active --limit 20
    python -m backend.active --min-sources 3  # only the richest stories

Clusters are skipped when they cannot produce a comparison: fewer than two
readable outlets means there is nothing to set side by side, and analysing them
burns fetch budget for a page that would say "no comparison available".
"""
import argparse
import sys
import time

from backend.analysis.runner import ClusterNotFound, analyze_cluster, set_status
from backend.config import ANALYSIS_FAILED, CLUSTER_MIN_COHERENCE
from backend.db.connection import get_cursor


def candidates(min_sources=2, min_coherence=CLUSTER_MIN_COHERENCE,
               include_done=False):
    """Clusters worth the fetch, richest first.

    Ordered by source count so that if the run is cut short - a timeout, a
    machine going to sleep - the stories with the most to compare are the ones
    that got done.
    """
    done_filter = "" if include_done else """
        AND NOT EXISTS (
            SELECT 1 FROM cluster_analysis ca
            WHERE ca.cluster_id = c.id AND ca.sources_used IS NOT NULL
        )
    """
    with get_cursor() as cur:
        cur.execute(f"""
            SELECT c.id,
                   count(DISTINCT a.source_name) AS sources,
                   c.article_count, c.coherence
            FROM clusters c
            JOIN cluster_members cm ON cm.cluster_id = c.id
            JOIN articles a ON a.id = cm.article_id
            WHERE c.coherence >= %s {done_filter}
            GROUP BY c.id, c.article_count, c.coherence
            HAVING count(DISTINCT a.source_name) >= %s
            ORDER BY count(DISTINCT a.source_name) DESC, c.coherence DESC
        """, (min_coherence, min_sources))
        return cur.fetchall()


def run(min_sources=2, limit=None, refresh=False):
    started = time.time()
    pending = candidates(min_sources=min_sources, include_done=refresh)
    if limit:
        pending = pending[:limit]

    if not pending:
        print("Every eligible cluster already has an analysis")
        return 0

    print(f"Analysing {len(pending)} clusters "
          f"({min_sources}+ sources, coherence >= {CLUSTER_MIN_COHERENCE})")

    done, failed, seconds = 0, 0, []
    for index, row in enumerate(pending, start=1):
        mark = time.time()
        label = f"[{index}/{len(pending)}] cluster {row['id']} ({row['sources']} src)"
        try:
            analyze_cluster(row["id"], refresh=True)
        except ClusterNotFound:
            # the cluster vanished under us: a re-clustering ran mid-batch
            print(f"  {label} gone - re-clustered mid-run")
            continue
        except Exception as exc:
            failed += 1
            # analyze_cluster already marked it failed; say why out loud too
            print(f"  {label} FAILED {type(exc).__name__}: {exc}")
            continue
        elapsed = time.time() - mark
        seconds.append(elapsed)
        done += 1
        print(f"  {label} {elapsed:.1f}s")

    total = time.time() - started
    print(f"\n{done} analysed, {failed} failed in {total:.1f}s")
    if seconds:
        seconds.sort()
        median = seconds[len(seconds) // 2]
        print(f"  per cluster: median {median:.1f}s, "
              f"slowest {seconds[-1]:.1f}s, fastest {seconds[0]:.1f}s")
        print(f"  a reader now opens any of these in ~50ms")
    return 1 if failed else 0


def status():
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.analysis_status, count(*) AS n
            FROM clusters c GROUP BY 1 ORDER BY 2 DESC
        """)
        print("cluster status:", {r["analysis_status"]: r["n"] for r in cur.fetchall()})
        cur.execute("""
            SELECT count(*) FILTER (WHERE title_summary IS NOT NULL) AS summarised,
                   count(*) FILTER (WHERE sources_used IS NOT NULL) AS analysed
            FROM cluster_analysis
        """)
        row = cur.fetchone()
        print(f"summarised: {row['summarised']}  fully analysed: {row['analysed']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-sources", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--refresh", action="store_true",
                        help="re-analyse clusters that already have results")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        status()
        sys.exit(0)
    sys.exit(run(min_sources=args.min_sources,
                 limit=args.limit or None,
                 refresh=args.refresh))
