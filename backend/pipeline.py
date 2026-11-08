"""The scheduled pipeline that keeps the live site current.

    python -m backend.pipeline                       # what the scheduled task runs
    python -m backend.pipeline --log logs\\pipeline.log
    python -m backend.pipeline --skip-ingest         # no feeds: compare and rebuild only

One run does, in order:

  1. the passive tier: collect from the feeds, group into stories when due,
     label them (backend/passive.py);
  2. the active tier: compare every story that has no comparison, including
     those a re-grouping just changed, whose old comparison was deleted
     (backend/active.py);
  3. the people pages, when the last build is more than a day old
     (backend/people.py).

Without step 2 the passive tier alone leaves more and more stories reading "not
compared yet"; without step 3 the people pages fall behind.

Each stage runs as its own process: the graphics memory one stage's models hold
is released before the next loads its own, and a crash in one stage is recorded
without stopping the others. A PostgreSQL advisory lock is held for the whole
run, so a run that outlasts the two-hour interval is never overlapped by the
next: the newcomer finds the lock taken and exits at once. The web API needs no
signal: it reads the database on every request, and PostgreSQL shows a reader
either the old grouping or the new one, never half of each.
"""
import argparse
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta

import psycopg2

from backend.db.connection import DB_CONFIG

# any fixed number: it names the lock, it is not a secret
LOCK_KEY = 72_310_401
# the people pages are rebuilt once a day: a person's portrayal moves slowly,
# and rebuilding means parsing and scoring every headline that names them
PEOPLE_EVERY = timedelta(hours=24)
# each stage is stopped if it runs past this; the scheduled task allows 1h50m
TIMEOUTS = {"passive": 45 * 60, "active": 45 * 60, "people": 15 * 60}
# no console window per stage when the scheduler starts us with pythonw.exe
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def acquire_lock():
    """A connection holding the run lock, or None if another run holds it."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
        if cur.fetchone()[0]:
            return conn
    conn.close()
    return None


def people_due(now=None, every=PEOPLE_EVERY):
    """(due, why): the people pages are rebuilt when missing or a day old."""
    now = now or datetime.now(UTC)
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('people') IS NOT NULL")
            if not cur.fetchone()[0]:
                return True, "no people table yet"
            cur.execute("SELECT max(built_at) FROM people")
            built = cur.fetchone()[0]
    finally:
        conn.close()
    return due_after(built, now, every)


def due_after(built, now, every=PEOPLE_EVERY):
    """(due, why) for a batch last built at `built`."""
    if built is None:
        return True, "never built"
    age = now - built
    hours = age.total_seconds() / 3600
    if age >= every:
        return True, f"last built {hours:.0f}h ago"
    return False, f"built {hours:.1f}h ago; next after {every.total_seconds() / 3600:.0f}h"


def stage(name, module, *args, timeout):
    """Run one stage in its own Python process; (ok, seconds). Its output is
    passed on line by line as it comes, so the log can be watched during a run,
    and the stage is stopped if it outlasts its timeout."""
    print(f"\n##### {name} #####", flush=True)
    started = time.time()
    process = subprocess.Popen([sys.executable, "-m", module, *args], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                               errors="replace", creationflags=NO_WINDOW,
                               env={**os.environ, "PYTHONUNBUFFERED": "1"})
    stopped = []

    def overrun():
        stopped.append(True)
        process.kill()

    watchdog = threading.Timer(timeout, overrun)
    watchdog.start()
    try:
        for line in process.stdout:
            print(line.rstrip("\n"), flush=True)
        code = process.wait()
    finally:
        watchdog.cancel()
    if stopped:
        print(f"STOPPED: still running after {timeout // 60} minutes", flush=True)
        code = "timeout"
    seconds = time.time() - started
    print(f"##### {name}: {'ok' if code == 0 else f'FAILED ({code})'} in {seconds:.0f}s", flush=True)
    return code == 0, seconds


def run(skip_ingest=False, people_every=PEOPLE_EVERY, force_people=False):
    print(f"=== Newseye pipeline | {datetime.now():%Y-%m-%d %H:%M} | database "
          f"{DB_CONFIG['dbname']} ===", flush=True)
    try:
        lock = acquire_lock()
    except psycopg2.OperationalError as exc:
        print(f"FAILED: database unreachable ({type(exc).__name__})")
        return 1
    if lock is None:
        print("another run is still going: this one stops here and changes nothing")
        return 0
    results = {}
    try:
        results["passive"] = stage("collect and group (passive tier)", "backend.passive",
                                   *(["--skip-ingest"] if skip_ingest else []),
                                   timeout=TIMEOUTS["passive"])
        # compare even if collecting failed: the stories already stored still
        # need their comparisons, and a feed outage should not stop that
        results["active"] = stage("compare (active tier)", "backend.active",
                                  timeout=TIMEOUTS["active"])
        due, why = (True, "asked for") if force_people else people_due(every=people_every)
        print(f"\npeople pages: {why}", flush=True)
        if due:
            results["people"] = stage("people pages", "backend.people", timeout=TIMEOUTS["people"])
    finally:
        lock.close()     # closing the connection releases the lock
    failed = [name for name, (ok, _) in results.items() if not ok]
    total = sum(seconds for _, seconds in results.values())
    print(f"\n=== pipeline done in {total:.0f}s: "
          + ", ".join(f"{name} {'ok' if ok else 'FAILED'} ({seconds:.0f}s)"
                      for name, (ok, seconds) in results.items()) + " ===", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    from backend.passive import _tee

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--skip-ingest", action="store_true", help="do not read the feeds")
    parser.add_argument("--people", action="store_true", help="rebuild the people pages now")
    parser.add_argument("--log", default=None, help="append all output to this file")
    args = parser.parse_args()
    with _tee(args.log):
        code = run(skip_ingest=args.skip_ingest, force_people=args.people)
    sys.exit(code)
