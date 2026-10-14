"""Does "where outlets differ" count only differences a reader can check?

Each case is a small analysis in the stored format. Facts some outlets did not
carry must not count: with several readable outlets nearly every fact is missing
from somebody, so counting omissions would rank every story the same.

    python -m backend.scripts.test_divergence
"""
import sys

from backend.analysis.divergence import differences


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


if __name__ == "__main__":
    passed = 0
    for name, analysis, wanted in CASES:
        got = differences(analysis)
        wrong = {k: got[k] for k, v in wanted.items() if got[k] != v}
        ok = not wrong
        passed += ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  got {wrong}'}")
    print(f"\n{passed}/{len(CASES)} divergence cases")
    sys.exit(0 if passed == len(CASES) else 1)
