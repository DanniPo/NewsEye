"""Does spaCy, with the Kenyan list and title rule, read Kenyan names correctly?

Each case is a sentence and what must, or must not, come out of it. Most were
real failures before the list existed or while it was being built: spaCy alone
called "Kindiki" an organisation, the first version of the title rule turned
"Narok Governor Patrick ole Ntutu" into "Patrick", and "Lusaka" has to stay a
city unless it is "Ken Lusaka".

Also checks the list itself: one person per alias, and no name both resolved
and deliberately left unresolved.

    python -m backend.scripts.test_entities
"""
import sys
from collections import defaultdict

from backend.nlp.entities import load_entities, load_nlp, spellings
from backend.scripts.testkit import case, report

# (sentence, entities that must appear as (text, label, id or None), texts that must not be PERSON)
CASES = [
    ("Former DP Gachagua hits back at Ruto's allies over the impeachment.",
     [("Gachagua", "PERSON", "rigathi-gachagua"), ("Ruto", "PERSON", "william-ruto")], []),
    ("Riggy G and Kalonzo met Jubilee officials at State House.",
     [("Riggy G", "PERSON", "rigathi-gachagua"), ("Kalonzo", "PERSON", "kalonzo-musyoka"),
      ("Jubilee", "ORG", "jubilee"), ("State House", "ORG", "state-house")], []),
    ("Uhuru says Raila won as crowds gather at Uhuru Park.",
     [("Uhuru", "PERSON", "uhuru-kenyatta"), ("Raila", "PERSON", "raila-odinga"),
      ("Uhuru Park", "FAC", None)], []),
    ("Matiang’i hits back at critics, and Fred Matiangi says he is ready.",
     [("Matiang’i", "PERSON", "fred-matiangi"), ("Fred Matiangi", "PERSON", "fred-matiangi")], []),
    ("Ken Lusaka addressed residents before flights to Lusaka resumed.",
     [("Ken Lusaka", "PERSON", "ken-lusaka")], ["Lusaka"]),
    ("Deputy President Kithure Kindiki toured Embu.",
     [("Kithure Kindiki", "PERSON", "kithure-kindiki"), ("Embu", "GPE", None)], []),
    ("IEBC Chairperson Erastus Ethekon announced the new timetable.",
     [("IEBC", "ORG", "iebc"), ("Erastus Ethekon", "PERSON", "erastus-ethekon")], []),
    ("Winnie Odinga and Oburu Oginga spoke, while Odinga's legacy was recalled.",
     [("Winnie Odinga", "PERSON", "winnie-odinga"), ("Oburu Oginga", "PERSON", "oburu-oginga"),
      ("Odinga", "PERSON", None)], []),
    ("Students at Kenyatta University protested on Friday.",
     [("Kenyatta University", "ORG", "kenyatta-university")], ["Kenyatta"]),
    ("The patient was buried at Langata Cemetery on Sunday.",
     [("Langata Cemetery", "FAC", None)], []),
    ("Leaders from Isiolo County backed the plan, said Senator Abdi Hassan Guyo.",
     [("Isiolo County", "GPE", None), ("Abdi Hassan Guyo", "PERSON", None)], []),
    # a namesake keeps spaCy's full name but not the listed person's identity
    ("The man claims to be the son of late Nyeri Governor Nderitu Gachagua.",
     [("Nderitu Gachagua", "PERSON", None)], []),
    ("Court directs the registry not to accept more petitions from man who claims to be "
     "late Nyeri Governor Nderitu Gachagua's son",
     [("Nderitu Gachagua", "PERSON", None)], []),
    # spaCy alone read the title and name together as an organisation
    ("CS Wendot noted that the agency will manage the site.",
     [("Wendot", "PERSON", None)], []),
    # names nobody listed, found by the title in front of them
    ("CS Mugaa and MP Wandeto toured Nyeri on Monday.",
     [("Mugaa", "PERSON", None), ("Wandeto", "PERSON", None), ("Nyeri", "GPE", None)], []),
    ("Narok Governor Patrick ole Ntutu urged the evictees to wait.",
     [("Patrick ole Ntutu", "PERSON", None)], ["Patrick"]),
    ("Murang’a Governor Irungu Kang’ata has announced 2,048 job opportunities.",
     [("Irungu Kang’ata", "PERSON", None)], []),
    ("Lady Justice Diana Rachel Kavedza ruled on the matter.",
     [("Diana Rachel Kavedza", "PERSON", None)], ["Lady"]),
    # the title rule must not invent people
    ("Governor Begins Probe Into Missing Funds", [], ["Begins Probe", "Begins"]),
    ("Ebola cases rise in DR Congo, says the Justice Ministry.", [], ["Congo", "Ministry"]),
    # names that are also ordinary words are matched only as written
    ("KURA will resurface the roads before the jubilee celebrations.",
     [("KURA", "ORG", "kura-acronym")], ["jubilee"]),
]


def check_list():
    """Problems in the list itself, as readable strings."""
    data = load_entities()
    problems, owner = [], defaultdict(set)
    ids = [e["id"] for e in data["people"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate person ids")
    for entry in data["people"]:
        for name in [entry["name"], *entry.get("aliases", [])]:
            for form in spellings(name):
                owner[form.lower()].add(entry["id"])
    for form, owners in owner.items():
        if len(owners) > 1:
            problems.append(f"'{form}' names {sorted(owners)}")
    for name in data["names_without_identity"]:
        if any(form.lower() in owner for form in spellings(name)):
            problems.append(f"'{name}' is both resolved and left unresolved")
    return problems


def entity(text, label, ident):
    return f"{text} = {label}" + (f" ({ident})" if ident else "")


def expectation(wanted, not_people):
    parts = [entity(*w) for w in wanted]
    if not_people:
        parts.append("not a person: " + ", ".join(not_people))
    return "; ".join(parts)


def results():
    problems = check_list()
    rows = [case(f"the list: {len(load_entities()['people'])} people, one person per alias",
                 "no problems", "; ".join(problems) or "no problems", not problems)]
    nlp = load_nlp()
    for text, wanted, not_people in CASES:
        doc = nlp(text)
        found = {(e.text, e.label_, e.ent_id_ or None) for e in doc.ents}
        people = {e.text for e in doc.ents if e.label_ == "PERSON"}
        missing = [w for w in wanted if w not in found]
        invented = [n for n in not_people if n in people]
        # everything spaCy returned, so a reader sees what else came out
        actual = "; ".join(entity(*f) for f in sorted(found, key=lambda f: text.find(f[0])))
        rows.append(case(text, expectation(wanted, not_people), actual or "no entities",
                         not missing and not invented))
    return rows


if __name__ == "__main__":
    sys.exit(report(results(), "entity cases"))
