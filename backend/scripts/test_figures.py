"""Verify figure parsing and the subject/unit gate on realistic claim sets.

These cases were written against find_figure_conflicts, which decided which
outlets disagreed. It is gone - no true positive on live data at 800 or 2,162
articles. The subject/unit gate it depended on is still the thing that decides
whether two figures may be shown side by side, so the cases now assert on
digest_groups: one group across two outlets, or none.

    python -m backend.scripts.test_figures
"""
from backend.analysis.digest import build_digest, digest_groups
from backend.analysis.figures import parse_figures, classify_measure

# pairs that must be grouped, and pairs that must not - the second list is the
# regression guard for the subject/unit matching
EXPECT_GROUPED = [
    ("floods missing", [
        {"text": "More than 1,300 missing after deadly floods swept away villages", "source": "Nation"},
        {"text": "At least 1,500 people are missing following the disaster", "source": "Standard"},
    ]),
    ("fdi vs foreign direct investment", [
        {"text": "Ruto said FDI more than doubled to $3.2 billion over the period", "source": "KBC"},
        {"text": "Foreign direct investment reached $2.8 billion, treasury data shows", "source": "Business Daily"},
    ]),
    ("compliance deadline", [
        {"text": "Ruto gives foreign traders 90 days to comply with the directive", "source": "Nairobi Wire"},
        {"text": "The directive gives traders 60 days before enforcement begins", "source": "People Daily"},
    ]),
    ("death toll", [
        {"text": "The death toll rose to 47 on Tuesday", "source": "Nation"},
        {"text": "Officials confirmed 52 dead in the incident", "source": "KBC"},
    ]),
    ("inflation", [
        {"text": "Inflation eased to 4.5 per cent in September", "source": "Business Daily"},
        {"text": "Inflation stood at 6.2 percent last month", "source": "Capital FM"},
    ]),
    # The adjudicator treated this as a non-conflict: one sum quoted in two
    # currencies is not two outlets disagreeing. The digest takes the opposite
    # view on purpose - currency is a label on the row, not a gate, so that a
    # reader can see that GBP1.6bn and $2.1bn are the same sale priced twice,
    # and can see when a figure does not say which money it means at all.
    ("same sum in two currencies", [
        {"text": "Dangote launched a £1.6bn share sale of the refinery", "source": "Capital FM"},
        {"text": "Bankers valued the refinery share sale at $2.1bn", "source": "Nation"},
    ]),
    ("seats won", [
        {"text": "The party said it won 47 seats in the assembly", "source": "Capital FM"},
        {"text": "Official tallies gave the party 39 seats in the assembly", "source": "Nation"},
    ]),
]

EXPECT_SEPARATE = [
    ("different things counted", [
        {"text": "The county opened 20 hospitals over the period", "source": "KBC"},
        {"text": "The county tarmacked 5 roads over the period", "source": "Nation"},
    ]),
    ("leaders vs trader days", [
        {"text": "The summit brought together 10,000 leaders from across the region", "source": "Nation"},
        {"text": "Traders were given 90 days to wind down their operations", "source": "KBC"},
    ]),
    ("reforms vs days", [
        {"text": "The government announced 50 reforms in the new policy framework", "source": "Nation"},
        {"text": "Ruto gives foreign traders 90 days to comply", "source": "KBC"},
    ]),
    ("investment vs defence budget", [
        {"text": "Foreign direct investment reached $2.8 billion, treasury data shows", "source": "Business Daily"},
        {"text": "The defence budget was raised to $3.2 billion this year", "source": "Nation"},
    ]),
    ("missing people vs unpaid teachers", [
        {"text": "More than 1,300 missing after deadly floods swept away villages", "source": "Nation"},
        {"text": "At least 1,500 teachers are yet to be paid, the union said", "source": "KBC"},
    ]),
    ("missing is not dead", [
        {"text": "More than 1,300 missing after deadly floods swept away villages", "source": "Nation"},
        {"text": "Officials confirmed 1,500 dead in the floods", "source": "KBC"},
    ]),
    ("same figure, one source only", [
        {"text": "The death toll rose to 47 on Tuesday", "source": "Nation"},
        {"text": "Officials later put the toll at 52 dead", "source": "Nation"},
    ]),
]

# Cases the current design cannot get right, kept visible rather than deleted.
KNOWN_LIMITATIONS = [
    # A government claim against an audit finding is a real disagreement and a
    # good one to show. It is also 4x apart with no casualty state, so the tight
    # non-casualty spread cap drops it. Loosening that cap to 5x recovers this
    # and simultaneously admits "KSh 1 trillion in savings" beside "$4 trillion
    # Africa holds", and "30 Hudson Yards" parsed as a headcount - both measured
    # on live clusters. Spread cannot separate those; subject and scope
    # discrimination is the real fix, and it is not built yet.
    ("hospitals built: claim vs audit", [
        {"text": "The president said his government built 20 hospitals in the county", "source": "KBC"},
        {"text": "An audit found only 5 hospitals were built in the county", "source": "Nation"},
    ], "dropped by the 3x non-casualty spread cap"),
]

PARSE_CASES = [
    "Ruto said FDI had more than doubled from $1.5 billion in 2022 to $3.2 billion",
    "Investment reached $2 billion according to treasury figures",
    "More than 1,300 missing after deadly floods swept away villages",
    "At least 1,500 people are missing following the disaster",
    "The death toll rose to 47 on Tuesday",
    "Officials confirmed 52 dead in the incident",
    "Ruto gives foreign traders 90 days to comply",
    "Traders were given 60 days under the new directive",
    "Inflation eased to 4.5 per cent in September",
    "Inflation stood at 6.2 percent last month",
]

MIXED_CLAIMS = [
    {"text": "More than 1,300 missing after deadly floods swept away villages", "source": "Nation"},
    {"text": "At least 1,500 people are missing following the disaster", "source": "Standard"},
    {"text": "Rescue teams said 1,320 remain missing in the region", "source": "Capital FM"},
    {"text": "Ruto said FDI more than doubled to $3.2 billion over the period", "source": "KBC"},
    {"text": "Foreign direct investment reached $2.8 billion, treasury data shows", "source": "Business Daily"},
    {"text": "Ruto gives foreign traders 90 days to comply with the directive", "source": "Nairobi Wire"},
    {"text": "The directive gives traders 60 days before enforcement begins", "source": "People Daily"},
]

print("=== PARSING ===")
for sentence in PARSE_CASES:
    figures = parse_figures(sentence)
    rendered = ", ".join(
        f"{f['text']}={f['value']:,.4g} [{f['unit'] or 'no unit'}]" for f in figures
    ) or "(none)"
    print(f"[{classify_measure(sentence):<10}] {rendered}")
    print(f"             {sentence[:78]}")

def cross_source_group(claims):
    """The first digest group spanning two or more outlets, if there is one."""
    for index, claim in enumerate(claims):
        claim.setdefault("article_id", index + 1)
    for group in digest_groups(build_digest(claims)):
        if len(group["sources"]) >= 2:
            return group
    return None


print("\n=== GROUPING A MIXED CLUSTER ===")
for group in digest_groups(build_digest(
        [dict(c, article_id=i + 1) for i, c in enumerate(MIXED_CLAIMS)])):
    print(f"\n{len(group['sources'])} outlets in '{group['unit']}' "
          f"(spread {group['spread']:.1f}x):")
    for row in group["values"]:
        print(f"   {row['figure']:>16}  [{row['source']}]")

print("\n=== SUBJECT/UNIT GATE ===")
failures = 0
for name, claims in EXPECT_GROUPED:
    group = cross_source_group(claims)
    ok = group is not None
    failures += not ok
    detail = (", ".join(f"{r['figure']}({r['source']})" for r in group["values"])
              if group else "not grouped")
    print(f"  {'PASS' if ok else 'FAIL'}  expect grouped   {name:<34} {detail}")

for name, claims in EXPECT_SEPARATE:
    group = cross_source_group(claims)
    ok = group is None
    failures += not ok
    detail = ("kept apart" if ok else
              "FALSE GROUP: " + ", ".join(f"{r['figure']}({r['source']})"
                                          for r in group["values"]))
    print(f"  {'PASS' if ok else 'FAIL'}  expect separate  {name:<34} {detail}")

print("\n=== KNOWN LIMITATIONS (not counted as failures) ===")
for name, claims, why in KNOWN_LIMITATIONS:
    group = cross_source_group(claims)
    print(f"  {'grouped' if group else 'KNOWN  '}  {name:<34} {why}")

total = len(EXPECT_GROUPED) + len(EXPECT_SEPARATE)
print(f"\n{total - failures}/{total} gate cases passed, "
      f"{len(KNOWN_LIMITATIONS)} known limitation(s)")
raise SystemExit(1 if failures else 0)
