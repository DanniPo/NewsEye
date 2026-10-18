"""Does the coverage table credit an outlet only with what it actually said?

Every pair below was grouped as "the same fact" by embedding similarity on a
real story, then checked by hand. Similarity alone credited Capital FM with KBC's
fact about the Ebola patient's citizenship when it had reported the patient's
route instead. With NLI checking each match, such an outlet is "related": shown
with its own sentence, neither credited nor counted as leaving the fact out.

The last case is the known limit: two outlets reporting the same auction with
different extra details, which NLI will not call the same. It must come out
related, never omitted - a false omission is the worst error this table can make.

    python -m backend.scripts.test_coverage
"""
import sys

from backend.analysis.consensus import analyze_cluster_claims
from backend.scripts.testkit import case, report

EBOLA_KBC = ("Health Cabinet Secretary Aden Duale, speaking to the press Tuesday on Ebola "
             "preparedness in Nairobi, said the patient was a Kenyan citizen living in the "
             "Democratic Republic of Congo (DRC) who died last night.")
EBOLA_CAPITAL = ("Health Cabinet Secretary Aden Duale confirmed the imported case on Tuesday, "
                 "saying the patient had travelled from the DRC through Uganda before entering "
                 "Kenya.")
WEAPONS_WIRE = ("Detectives processing the scene recovered several weapons covered in bloodstains "
                "near the body, including an axe, a panga, and two knives.")
WEAPONS_CAPITAL = ("Detectives who responded to the scene recovered several weapons, including an "
                   "axe, panga and two knives, which police said had bloodstains and were found "
                   "near the body.")
HOUSING_KNA = ("Nearly nine out of 10 Kenyans are being forced to cut back on essential spending "
               "to meet housing costs, a new survey by Habitat for Humanity International has "
               "revealed.")
HOUSING_WIRE = ("Sixty-two percent of Kenyans say housing costs make it difficult to consider "
                "starting a family, compared to 56 percent globally.")
AUCTION_KBC = ("The final auction, Sale 42, held on September 29, however, reflected some softening "
               "in prices as the season came to an end, with 17,765 bags earning farmers Sh841.3 "
               "million.")
AUCTION_WIRE = ("The season closed with Sale 42 on September 29, 2026, in which 17,765 bags fetched "
                "KSh 841.3 million.")

# (name, [(source, text)], readable outlets, unread outlets, outlet checked, expected state)
CASES = [
    ("different facts about the Ebola patient",
     [("KBC", EBOLA_KBC), ("Capital FM", EBOLA_CAPITAL)],
     ["KBC", "Capital FM"], [], "Capital FM", "related"),
    ("the same weapons, told two ways",
     [("Nairobi Wire", WEAPONS_WIRE), ("Capital FM", WEAPONS_CAPITAL)],
     ["Nairobi Wire", "Capital FM"], [], "Capital FM", "reported"),
    ("two different figures from one survey",
     [("Kenya News", HOUSING_KNA), ("Nairobi Wire", HOUSING_WIRE)],
     ["Kenya News", "Nairobi Wire"], [], "Nairobi Wire", "related"),
    ("an outlet with nothing like the fact omitted it",
     [("Nairobi Wire", WEAPONS_WIRE), ("Capital FM", WEAPONS_CAPITAL)],
     ["Nairobi Wire", "Capital FM", "Nation Africa"], [], "Nation Africa", "omitted"),
    ("an outlet we could not read never omits",
     [("Nairobi Wire", WEAPONS_WIRE), ("Capital FM", WEAPONS_CAPITAL)],
     ["Nairobi Wire", "Capital FM"], ["People Daily"], "People Daily", "neither"),
    ("known limit: the same auction with different details",
     [("KBC", AUCTION_KBC), ("Nairobi Wire", AUCTION_WIRE)],
     ["KBC", "Nairobi Wire"], [], "Nairobi Wire", "related"),
]


def state_of(row, outlet):
    if outlet in row["reported_by"]:
        return "reported"
    if outlet in {r["source"] for r in row["related"]}:
        return "related"
    if outlet in row["omitted_by"]:
        return "omitted"
    return "neither"


def results():
    found = []
    for name, said, readable, unread, outlet, wanted in CASES:
        claims = [{"text": text, "source": source} for source, text in said]
        rows = analyze_cluster_claims(claims, all_sources=readable, unread_sources=unread)
        got = state_of(rows[0], outlet) if rows else "not grouped"
        found.append(case(name, f"{outlet}: {wanted}", f"{outlet}: {got}", got == wanted))
    return found


if __name__ == "__main__":
    sys.exit(report(results(), "coverage cases"))
