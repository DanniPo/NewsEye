"""Does "where outlets differ" count only differences a reader can check?

Each case is a small analysis in the stored format. Facts some outlets did not
carry must not count: with several readable outlets nearly every fact is missing
from somebody, so counting omissions would rank every story the same.

    python -m backend.scripts.test_divergence
"""
import sys
from unittest import mock

from backend.analysis.divergence import differences
from backend.scripts.testkit import case, fields, report


def fact(reported, omitted=(), related=()):
    return {"anchor": {"text": "a fact"}, "reported_by": list(reported),
            "omitted_by": list(omitted),
            "related": [{"source": s, "text": "close wording"} for s in related]}


def figure(source, value, text):
    # the digest row fields digest_groups needs to put two figures side by side
    return {"tier": "shared", "value": value, "figure": text, "unit": "people", "state": "dead",
            "currency": "unspecified", "source": source, "credited_to": None,
            "cumulative": False, "scope": [], "named": [], "subject": ["killed", "crash"],
            "acronyms": [], "upper": [], "sentence": f"{text} people were killed in the crash",
            "context": f"{text} people were killed in the crash", "url": None}


CASES = [
    ("omissions alone are not a difference",
     {"consensus": [fact(["KBC"], omitted=["Nation Africa", "Capital FM"])]},
     {"score": 0}),
    ("related wording counts once per fact",
     {"consensus": [fact(["KBC"], related=["Capital FM", "Nation Africa"]), fact(["KBC"])]},
     {"related": 1, "score": 1}),
    ("reworded and shortened quotes count, identical ones do not",
     {"quotes": [{"versions": [{"relation": "first"}, {"relation": "same"},
                               {"relation": "says less"}, {"relation": "worded differently"}]}]},
     {"quotes": 2}),
    ("a wide tone gap about one person counts once",
     {"framing": [{"entity": "William Ruto", "sources": [{"score": -0.4}, {"score": 0.3}]}]},
     {"score": 1}),
    ("a narrow tone gap does not",
     {"framing": [{"entity": "William Ruto", "sources": [{"score": 0.1}, {"score": 0.3}]}]},
     {"score": 0}),
    ("two outlets with different death tolls",
     {"figure_digest": [figure("KBC", 12, "12"), figure("Nation Africa", 17, "17")]},
     {"figures": 1}),
]


def results():
    rows = []
    for name, analysis, wanted in CASES:
        got = differences(analysis)
        actual = {key: got[key] for key in wanted}
        rows.append(case(name, fields(wanted), fields(actual), actual == wanted))

    # last, so the case ids cited elsewhere stay as they are. Counting figure
    # groups needs no ordering by meaning, so it must not load the language model:
    # it did, and the first story list after the API started took 19 s (DEF-46)
    def no_model(members):
        raise AssertionError("the figure groups were ordered by meaning just to be counted")

    with mock.patch("backend.analysis.digest.rank_by_similarity", side_effect=no_model):
        try:
            got = differences({"figure_digest": [figure("Nation", 47, "47"), figure("KBC", 52, "52")]})
            actual, ok = f"different figures in {got['figures']} group, model not loaded", got["figures"] == 1
        except AssertionError as exc:
            actual, ok = str(exc), False
    rows.append(case("counting differences does not load the language model (DEF-46)",
                     "different figures in 1 group, model not loaded", actual, ok))
    return rows


if __name__ == "__main__":
    sys.exit(report(results(), "divergence cases"))
