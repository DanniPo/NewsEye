import argparse
import contextlib
import io
import os
import sys
import time
from datetime import UTC, datetime, timedelta

# Progress bars are drawn with carriage returns for a terminal that redraws in
# place. Appended to a file they become one unreadable line per model load. This
# is the unattended entry point, so there is never anyone watching them.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")

from backend.db.connection import get_cursor

# re-cluster when this many new articles have landed since the last run...
CLUSTER_MIN_NEW_ARTICLES = 40
# ...or when the clustering is simply this old, whichever comes first
CLUSTER_MAX_AGE_HOURS = 20


def _state():
    """Corpus size and the age of the current clustering.

    Returns None when the database cannot be reached. A scheduled run must exit
    with a code rather than a traceback: an unhandled psycopg2 error looks the
    same to Task Scheduler as a crash in the middle of clustering.
    """
    try:
        return _read_state()
    except Exception:
        return None


def _read_state():
    with get_cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM articles")
        articles = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n, max(created_at) AS latest FROM clusters")
        row = cur.fetchone()
        # Articles ingested since the last clustering - NOT articles lacking a
        # cluster membership. HDBSCAN leaves roughly half the window as noise and
        # noise never joins cluster_members, so the "unclustered" count never
        # fell below ~225 and clustering fired on every single run.
        if row["latest"] is not None:
            cur.execute("""
                SELECT count(*) AS n FROM articles
                WHERE inserted_at_utc > %s
            """, (row["latest"],))
            fresh = cur.fetchone()["n"]
        else:
            fresh = articles
    return {
        "articles": articles,
        "clusters": row["n"],
        "clustered_at": row["latest"],
        "new_since_clustering": fresh,
    }


def _cluster_is_due(state, force=False):
    if force or not state["clusters"]:
        return True, "no clustering on record" if not state["clusters"] else "forced"
    if state["new_since_clustering"] >= CLUSTER_MIN_NEW_ARTICLES:
        return True, f"{state['new_since_clustering']} articles ingested since last clustering"
    stamp = state["clustered_at"]
    if stamp is not None:
        age = datetime.now(UTC) - stamp
        if age >= timedelta(hours=CLUSTER_MAX_AGE_HOURS):
            return True, f"clustering is {age.total_seconds() / 3600:.0f}h old"
        return False, (f"only {state['new_since_clustering']} new articles and "
                       f"clustering is {age.total_seconds() / 3600:.0f}h old - skipping")
    return True, "clustering timestamp missing"


def run(force_cluster=False, ingest_only=False, skip_ingest=False):
    started = time.time()
    failures = []
    # Per-stage timings, kept so the summary can separate real work from time the
    # process merely existed. A run that straddles a sleep looks identical to a
    # hang otherwise: one scheduled run reported "done in 11632.0s" because the
    # trigger woke the laptop, the laptop went straight back into Modern Standby,
    # and the process sat frozen mid-import for 3.2 hours.
    stages = {}
    print(f"=== Newseye passive tier | {datetime.now():%Y-%m-%d %H:%M} ===")

    before = _state()
    if before is None:
        print("FAILED: database unreachable")
        return 1
    print(f"corpus: {before['articles']} articles, {before['clusters']} clusters")

    if not skip_ingest:
        print("\n-- ingest --")
        mark = time.time()
        try:
            # importing this pulls in torch, which is ~2GB of CUDA DLLs. It is
            # timed separately because it regularly dwarfs the ingest itself and
            # used to be billed to it, making ingestion look pathologically slow.
            from backend.ingestion.runner import run_ingestion
            stages["model load"] = time.time() - mark
            print(f"  models loaded in {stages['model load']:.1f}s")
            mark = time.time()
            run_ingestion()
        except Exception as exc:
            failures.append(f"ingest: {type(exc).__name__}: {exc}")
            print(f"  FAILED: {type(exc).__name__}: {exc}")
        stages["ingest"] = time.time() - mark
        print(f"  {stages['ingest']:.1f}s")

    if ingest_only:
        print("\n--ingest-only: stopping before clustering")
        return _finish(started, failures, stages)

    state = _state()
    if state is None:
        print("\nFAILED: database unreachable after ingest")
        return 1
    due, why = _cluster_is_due(state, force_cluster)
    print(f"\n-- cluster -- ({why})")
    if not due:
        return _finish(started, failures, stages)

    mark = time.time()
    try:
        from backend.nlp.clustering import DegenerateClustering, run_clustering
        try:
            n_clusters, n_noise = run_clustering()
            print(f"  {n_clusters} clusters, {n_noise} noise")
        except DegenerateClustering as exc:
            # not a crash: the guard did its job and left the old clusters alone
            print(f"  REJECTED, previous clustering kept: {exc}")
            failures.append(f"clustering rejected: {exc}")
            stages["cluster"] = time.time() - mark
            return _finish(started, failures, stages)
    except Exception as exc:
        failures.append(f"cluster: {type(exc).__name__}: {exc}")
        print(f"  FAILED: {type(exc).__name__}: {exc}")
        stages["cluster"] = time.time() - mark
        return _finish(started, failures, stages)
    stages["cluster"] = time.time() - mark
    print(f"  {stages['cluster']:.1f}s")

    print("\n-- summaries --")
    mark = time.time()
    try:
        from backend.nlp.previews import generate_previews
        generate_previews()
    except Exception as exc:
        failures.append(f"summaries: {type(exc).__name__}: {exc}")
        print(f"  FAILED: {type(exc).__name__}: {exc}")
    stages["summaries"] = time.time() - mark
    print(f"  {stages['summaries']:.1f}s")

    return _finish(started, failures, stages)


def _finish(started, failures, stages=None):
    after = _state()
    wall = time.time() - started
    worked = sum((stages or {}).values())
    print(f"\n=== done in {wall:.1f}s ({worked:.1f}s of it working) ===")
    if stages:
        print("  " + ", ".join(f"{k} {v:.1f}s" for k, v in stages.items()))
    # Anything left over is time the process was not running: the machine asleep,
    # or Windows throttling it. Named explicitly so it is never mistaken for work.
    unaccounted = wall - worked
    if unaccounted > 60:
        print(f"  {unaccounted:.0f}s unaccounted - machine asleep or I/O throttled, "
              f"not time spent computing")
    print(f"corpus: {after['articles']} articles, {after['clusters']} clusters")
    with get_cursor() as cur:
        cur.execute("""
            SELECT count(*) AS n FROM cluster_analysis WHERE title_summary IS NOT NULL
        """)
        print(f"summarised: {cur.fetchone()['n']}/{after['clusters']}")
    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
    return 1 if failures else 0


@contextlib.contextmanager
def _tee(path):
    """Send everything printed to a log file as well as stdout.

    The scheduled task runs under pythonw.exe, which has no console at all -
    that is what keeps a PowerShell window from appearing on the desktop every
    two hours. With no console, print() has nowhere to go, so the run has to
    write its own log rather than relying on shell redirection.
    """
    if not path:
        yield
        return

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        class _Fan(io.TextIOBase):
            def write(self, text):
                handle.write(text)
                handle.flush()
                # stdout is None under pythonw; writing to it would raise
                if sys.__stdout__ is not None:
                    try:
                        sys.__stdout__.write(text)
                    except Exception:
                        pass
                return len(text)

        fan = _Fan()
        with contextlib.redirect_stdout(fan), contextlib.redirect_stderr(fan):
            yield


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster", action="store_true",
                        help="cluster even if not due")
    parser.add_argument("--ingest-only", action="store_true")
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--log", default=None,
                        help="append all output to this file (needed under pythonw)")
    args = parser.parse_args()
    with _tee(args.log):
        code = run(force_cluster=args.cluster,
                   ingest_only=args.ingest_only,
                   skip_ingest=args.skip_ingest)
    sys.exit(code)
