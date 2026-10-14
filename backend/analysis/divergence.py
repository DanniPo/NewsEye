"""Where outlets' coverage of one story differs, and in what way.

Read from a finished deep analysis, so it ranks only stories that have been
analysed. Every part is something a reader can check on the story page:

    related   facts where an outlet said something close but not the same
              (the coverage table's related cells)
    figures   groups where outlets published different numbers for one quantity
    quotes    remarks an outlet quoted shorter, longer or in other words
    framing   two outlets far apart in tone about the same named person

"Facts not carried by all" is left out on purpose. With four or more readable
outlets almost every fact is missing from somebody - it was 100% in half the
stories measured - so it cannot tell one story from another.

Nothing here says which outlet is right, or that any outlet is biased. The
score is a count of checkable differences, and wherever it is shown its
reasons are shown with it.
"""
from backend.analysis.digest import digest_groups

# sentiment runs -1..1; outlets this far apart about one person count once
FRAMING_GAP = 0.5
CHANGED = ("worded differently", "says less", "says more")


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def differences(analysis):
    """{"score", "reasons", and each count} for one analysed story."""
    groups = analysis.get("consensus") or []
    related = sum(1 for g in groups if g.get("related"))
    figures = sum(1 for g in digest_groups(analysis.get("figure_digest") or [])
                  if len({v["figure"] for v in g["values"]}) > 1)
    quotes = sum(1 for remark in analysis.get("quotes") or []
                 for v in remark["versions"] if v["relation"] in CHANGED)
    widest, entity = 0.0, None
    for record in analysis.get("framing") or []:
        scores = [s["score"] for s in record.get("sources") or []]
        if len(scores) > 1 and max(scores) - min(scores) > widest:
            widest, entity = max(scores) - min(scores), record.get("entity")
    framing = int(widest >= FRAMING_GAP)

    reasons = []
    if related:
        reasons.append(f"outlets worded {_plural(related, 'fact')} differently")
    if figures:
        reasons.append(f"different figures in {_plural(figures, 'group')}")
    if quotes:
        reasons.append(f"{_plural(quotes, 'quote')} shortened or reworded")
    if framing:
        reasons.append(f"tone about {entity} differs between outlets")
    return {"score": related + figures + quotes + framing, "reasons": reasons,
            "related": related, "figures": figures, "quotes": quotes,
            "framing_gap": round(widest, 2)}
