"""Store how each outlet presents every listed person, for the API's people pages.

    python -m backend.people

Portraying one person parses every stored headline and opening line that names
them and scores the tone of each, which takes seconds - far too slow for a web
request. So, like the active tier, it runs as a batch and the API only reads the
result. The numbers come from the same code as the static site's people pages
(build_site.people_data), so the two cannot disagree.

The table is replaced whole in one transaction: a reader never sees a half-built
set of people, and a person who drops below the comparison threshold disappears.
"""
import json
import sys
import time

from backend.db.connection import get_cursor
from backend.scripts.build_site import people_data


def jsonable(outlets):
    """Each outlet's summary in a form JSON can hold.

    acted_on counts (verb, actor) pairs, and JSON keys must be strings, so it is
    stored as a list of {"verb", "by", "count"}, most frequent first.
    """
    return {outlet: {**summary,
                     "acted_on": [{"verb": verb, "by": by, "count": count}
                                  for (verb, by), count in
                                  summary.get("acted_on", {}).most_common()]}
            for outlet, summary in outlets.items()}


def store(data):
    """Replace the people table with one build's results. Returns the row count."""
    rows = [(p["id"], p["name"], json.dumps(p.get("aliases", [])), p["articles"],
             json.dumps(jsonable(p["outlets"]), default=str),
             json.dumps(p["totals"], default=str),
             data["first"], data["last"])
            for p in data["people"]]
    with get_cursor() as cur:
        cur.execute("DELETE FROM people")
        cur.executemany("""
            INSERT INTO people (id, name, aliases, articles, outlets, totals,
                                period_first, period_last)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, rows)
    return len(rows)


def main():
    started = time.time()
    print("Portraying every listed person...")
    data = people_data()
    if data is None:
        print("No people data (see the message above); the table was left as it was.")
        return 1
    count = store(data)
    print(f"Stored {count} people in {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
