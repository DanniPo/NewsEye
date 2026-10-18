"""What every test script reports: one record per case, printed or kept.

Each test script exposes results(), a list of cases, each with what was
expected, what actually came out, and whether the two agree. Run on its own, a
script prints them; test_record.py runs every script and keeps the record.

REQUIREMENTS is what the tests trace to: every case names the requirement it
gives evidence for, so a result can be read against what the system must do.
"""

REQUIREMENTS = {
    "FR-01": "Collect articles from the RSS feeds of 12 Kenyan outlets, de-duplicated, "
             "each with an embedding and a topic",
    "FR-02": "Group articles reporting the same event into stories that keep their id "
             "as news arrives",
    "FR-03": "Recognise Kenyan people, institutions and places",
    "FR-04": "Show which outlets carried each fact, which said something related, and "
             "which could not be read",
    "FR-05": "Show who was quoted and how each outlet's version of a remark differs",
    "FR-06": "Show each outlet's figures, side by side only when they count the same thing",
    "FR-07": "Show how each outlet presents a named person",
    "FR-08": "Point the reader to the stories where outlets differ most",
    "FR-09": "Publish a static site - dashboard, story, people and search pages - that "
             "can also be sent as one file",
    "FR-10": "Search the collection by meaning",
    "NFR-01": "Performance: passive run within 5 minutes; one story analysed within 30 s",
    "NFR-02": "Reliability: a failing feed, database or clustering is reported and never "
              "damages stored stories",
    "NFR-03": "Security: third-party feed content cannot inject markup or script; no "
              "credentials in the repository",
    "NFR-04": "Neutrality: no verdicts or scores; an outlet that could not be read is "
              "never counted as leaving anything out",
}


def case(name, expected, actual, ok, trace=None):
    """One case. ok is None for a known limitation: recorded, never counted.

    trace names the requirement(s) the case gives evidence for; without it the
    suite's own requirement applies."""
    return {"case": name, "expected": expected, "actual": actual, "ok": ok, "trace": trace}


def verdict(row):
    if row["ok"] is None:
        return "KNOWN"
    return "PASS" if row["ok"] else "FAIL"


def fields(values):
    """{"role": "speaks", "verb": "claim"} -> "role speaks, verb claim"."""
    return ", ".join(f"{key} {value}" for key, value in values.items())


def report(rows, noun):
    """Print one line per case, with expected and actual where they differ.

    Returns the exit code: 0 only when every counted case passed.
    """
    for row in rows:
        detail = ""
        if not row["ok"]:
            detail = (f"\n        expected  {row['expected']}"
                      f"\n        got       {row['actual']}")
        print(f"  {verdict(row):<5} {row['case'][:74]}{detail}")
    counted = [r for r in rows if r["ok"] is not None]
    passed = sum(1 for r in counted if r["ok"])
    known = len(rows) - len(counted)
    print(f"\n{passed}/{len(counted)} {noun}"
          + (f", {known} known limitation(s)" if known else ""))
    return 0 if passed == len(counted) else 1
