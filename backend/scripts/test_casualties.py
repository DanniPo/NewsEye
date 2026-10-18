"""Does the figure digest group casualty counts that belong together?

Money proved undetectable: currencies, retail-vs-institutional pricing, gross vs
net and differing timeframes mean two different numbers are usually two different
quantities. Casualty counts are the opposite case - "how many died in this
incident" is one quantity, and outlets genuinely disagree about it because police,
hospitals and rights groups count differently.

These cases were written against find_figure_conflicts, which decided *for* the
reader which outlets disagreed. That function is gone - it produced no true
positive on live data at either 800 or 2,162 articles. The cases survive because
the underlying question did not change, only who answers it: the digest's job is
to put two figures side by side when they are rival counts of one thing, and to
keep them apart when they are not. The reader draws the conclusion.

So SHOULD_GROUP means "these two belong in one comparable group" and
SHOULD_SEPARATE means "showing these side by side would mislead".

    python -m backend.scripts.test_casualties
"""
import sys
from datetime import UTC, datetime, timedelta

from backend.analysis.digest import build_digest, digest_groups
from backend.scripts.testkit import case, report

T0 = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)
def at(hours):
    return T0 + timedelta(hours=hours)

# realistic disagreements: the same incident, counted by different authorities
SHOULD_GROUP = [
    ("road accident: police vs hospital", [
        {"text": "Police said 12 people died when the bus rolled at Salgaa on Sunday", "source": "Nation"},
        {"text": "Hospital records show 17 people died in the Salgaa bus crash", "source": "Standard"},
    ]),
    ("protest: police vs rights group", [
        {"text": "Police confirmed 3 protesters were killed during Tuesday's demonstrations", "source": "KBC"},
        {"text": "The rights commission says 11 protesters were killed in the demonstrations", "source": "Nation"},
    ]),
    ("attack: military vs county officials", [
        {"text": "The military said 8 civilians were killed in the raid on the village", "source": "KBC"},
        {"text": "County officials put the number killed in the raid at 23 civilians", "source": "Capital FM"},
    ]),
    ("building collapse: injured count", [
        {"text": "At least 40 people were injured when the building collapsed", "source": "Capital FM"},
        {"text": "Rescue teams said 62 people were injured in the collapse", "source": "People Daily"},
    ]),
    ("simultaneous reports, different tolls", [
        {"text": "Police said 3 protesters were killed in Tuesday's demonstrations",
         "source": "KBC", "published_utc": at(0)},
        {"text": "Medics said 11 protesters were killed in Tuesday's demonstrations",
         "source": "Nation", "published_utc": at(1)},
    ]),
    ("same place, two authorities", [
        {"text": "In Nepal, police said 558 people were missing after the floods",
         "source": "K24 Digital", "entities": [["Nepal", "GPE"]]},
        {"text": "In Nepal, the Red Cross put the number missing at 826",
         "source": "People Daily", "entities": [["Nepal", "GPE"]]},
    ]),
    ("spelled-out counts still compare", [
        {"text": "Police said five people were killed in the Gotu ambush",
         "source": "KBC", "entities": [["Gotu", "GPE"]]},
        {"text": "Residents said eight people were killed in the Gotu ambush",
         "source": "Capital FM", "entities": [["Gotu", "GPE"]]},
    ]),
    ("flood: missing count", [
        {"text": "More than 1,300 remain missing after the floods swept the valley", "source": "Nation"},
        {"text": "Officials say 1,500 are still missing following the floods", "source": "Standard"},
    ]),
    # a toll that grew is still worth showing side by side - the digest orders by
    # date so it reads as a timeline. What must never happen is calling it a
    # disagreement between the outlets, and nothing here does that any more.
    ("evolving toll, same incident", [
        {"text": "The death toll from the Salgaa crash rose to 12 on Sunday evening",
         "source": "Nation", "published_utc": at(0)},
        {"text": "The Salgaa crash death toll climbed to 17 by Tuesday morning",
         "source": "Standard", "published_utc": at(40)},
    ]),
]

# pairs that would mislead a reader if shown as rival counts of one number
SHOULD_SEPARATE = [
    ("dead is not injured", [
        {"text": "Police said 12 people died when the bus rolled at Salgaa", "source": "Nation"},
        {"text": "A further 30 people were injured when the bus rolled at Salgaa", "source": "Standard"},
    ]),
    ("dead is not missing", [
        {"text": "Officials confirmed 40 people died in the floods that hit the valley", "source": "Nation"},
        {"text": "Another 62 people are missing after the floods hit the valley", "source": "KBC"},
    ]),
    # entities are attached because production always has them: without a place,
    # two crashes on the same day are indistinguishable, and this case used to
    # pass only because "Seven" was spelled out and therefore invisible
    ("different incidents", [
        {"text": "Police said 12 people died in the Salgaa bus crash on Sunday",
         "source": "Nation", "entities": [["Salgaa", "GPE"]]},
        {"text": "Seven people died in a matatu collision on Mombasa Road on Monday",
         "source": "KBC", "entities": [["Mombasa Road", "LOC"]]},
    ]),
    ("cumulative vs single incident", [
        {"text": "Police said 4 people died in Sunday's crash at the black spot", "source": "Nation"},
        {"text": "Road deaths have reached 3,200 nationally since January, NTSA said", "source": "Standard"},
    ]),
    ("one outlet quoting two authorities", [
        {"text": "Police said 12 people died in the Salgaa bus crash", "source": "Nation"},
        {"text": "The hospital later put the Salgaa crash toll at 17 people dead", "source": "Nation"},
    ]),
    ("parts of a disaster are not the whole", [
        {"text": "On the Chinese side, at least 558 people were still missing",
         "source": "K24 Digital", "entities": [["Chinese", "NORP"]]},
        {"text": "In Nepal, the number of people reported missing rose to 826",
         "source": "People Daily", "entities": [["Nepal", "GPE"]]},
    ]),
]


def _grouped_across_sources(claims):
    """Did the digest place figures from two different outlets in one group?"""
    for index, claim in enumerate(claims):
        claim.setdefault("article_id", index + 1)
    groups = digest_groups(build_digest(claims))
    for group in groups:
        if len(group["sources"]) >= 2:
            return group
    return None


def outcome(group):
    """What the digest did with a pair, in words."""
    if group is None:
        return "kept apart"
    return (f"grouped as {group['unit']}: "
            + ", ".join(f"{r['figure']} ({r['source']})" for r in group["values"]))


def results():
    rows = []
    for name, claims in SHOULD_GROUP:
        group = _grouped_across_sources(claims)
        rows.append(case(name, "grouped: rival counts of one thing", outcome(group),
                         group is not None))
    for name, claims in SHOULD_SEPARATE:
        group = _grouped_across_sources(claims)
        rows.append(case(name, "kept apart: side by side would mislead", outcome(group),
                         group is None))
    return rows


if __name__ == "__main__":
    # this script once printed MISS and FALSE GROUP but always exited 0, so a
    # regression here could never fail CI
    sys.exit(report(results(), "casualty cases"))
