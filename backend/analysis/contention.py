"""How contested a story is, from what its headlines and quotes report.

A story counts as contested when its headlines report a dispute - who "slams",
"accuses" or "denies" whom, or a row, probe, arrest or protest - and when its
outlets quote someone criticising, denying or defending. That is what the
coverage reports, not a finding that the outlets disagree: Newseye never says
who is right.

Used by pick_showcase.py (a demonstration set), export_review.py --contested
(the latest contested stories) and the site's Contested page.
"""
import re

from backend.analysis.verbs import family_of
from backend.config import REPORTING_VERBS

CONTESTED = ("criticised", "denied or defended")


def _verb_pattern(verb):
    """'accuse' matches accuses/accused/accusing, 'deny' denies/denied/denying; 'hit
    back' only as a phrase, never bare 'hits' - which matched "milk output hits 5.2B
    litres"."""
    first, _, rest = verb.partition(" ")
    if first.endswith("y") and first[-2] not in "aeiou":
        stem = re.escape(first[:-1]) + "(?:y|ies|ied|ying)"
    elif first.endswith("e"):
        stem = re.escape(first[:-1]) + r"(?:e\w{0,3}|ing)"
    else:
        stem = re.escape(first) + r"\w{0,4}"
    return stem + (r"\s+" + re.escape(rest) if rest else "")


CONFLICT = re.compile(r"\b(" + "|".join(_verb_pattern(v) for family in CONTESTED
                                       for v in REPORTING_VERBS[family]) + r")\b", re.I)
# Controversy also shows in what a headline is about, not only in who "slams"
# whom: a probe, a row, an arrest. Verbs alone left nearly every story at zero.
CONTROVERSY = re.compile(
    r"\b(rows?|disputes?|disputed|clash(es|ed)?|protests?|protesters|impeach\w*|probes?|"
    r"probed|scandals?|petitions?|arrest(s|ed)?|murder(s|ed)?|kill(s|ed|ings?)?|crackdown|"
    r"ultimatum|rift|feud|showdown|war|attacks?|attacked|standoff|outcry|backlash|fraud|"
    r"corruption|graft|sack(s|ed)?|suspend(s|ed)?|ousts?|ousted|defy|defies|condemns?|"
    r"condemned|demands?|warns?|threat(s|ens)?|bans?|banned|evict\w*|demoli\w*|"
    r"court|charged|accused|controversy|controversial|uproar|fury|anger)\b", re.I)
CONTESTED_TOPICS = {"Politics", "Security"}
# Below this a story is not listed as contested: half its headlines reporting a
# dispute, or fewer in a political or security story with criticism quoted. One
# headline in ten mentioning a protest put a memorial on the list.
LISTED = 0.5


def disputed(titles):
    """How many of these headlines report a dispute."""
    return sum(1 for t in titles if CONFLICT.search(t) or CONTROVERSY.search(t))


def headline_score(titles, topic=None):
    """Share of headlines that report a dispute, plus a quarter for a political
    or security story."""
    if not titles:
        return 0.0
    return disputed(titles) / len(titles) + (0.25 if topic in CONTESTED_TOPICS else 0.0)


def contested_quotes(remarks):
    """Quotes an outlet reported as criticism, denial or defence."""
    return sum(1 for r in remarks or () for v in r["versions"]
               if family_of(v.get("verb")) in CONTESTED)


def contention(titles, topic=None, remarks=None):
    """(score, reasons) for an analysed story: the headline score plus a quarter
    for each quote reported as criticism, denial or defence. The reasons say
    what was counted, so a story's place on a list is never a mystery."""
    quotes = contested_quotes(remarks)
    score = headline_score(titles, topic) + 0.25 * quotes
    reasons = []
    found = disputed(titles)
    if found:
        reasons.append(f"{found} of {len(titles)} headlines report a dispute")
    if quotes:
        reasons.append(f"{quotes} quote{'s' if quotes > 1 else ''} reported as criticism "
                       "or denial")
    if score and topic in CONTESTED_TOPICS:
        reasons.append(topic)
    return score, reasons
