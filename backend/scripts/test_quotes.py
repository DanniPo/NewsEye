"""Does quote extraction find the words, the speaker, and how outlets differ?

Extraction cases are the attribution forms Kenyan outlets use. Alignment cases
are two outlets quoting one speaker: identically, one trimming the other, or
two different remarks that must not be lined up as one.

    python -m backend.scripts.test_quotes
"""
import sys

from backend.analysis.quotes import align_quotes, extract_quotes

# (text, expected fields of the first quote found; None means no quote at all)
EXTRACT = [
    ("“We will not allow anyone to intimidate voters,” Kindiki said on Tuesday.",
     {"speaker": "Kithure Kindiki", "verb": "say", "how": "named"}),
    ("Gachagua said: “The government is plotting to arrest me before the rally.”",
     {"speaker": "Rigathi Gachagua", "how": "named"}),
    ("Treasury CS John Mbadi addressed traders in Mombasa on Monday. "
     "“The economy is recovering faster than expected,” he said.",
     {"speaker": "John Mbadi", "how": "pronoun"}),
    ("According to IEBC chairperson Erastus Ethekon, “the register will be audited "
     "before March.”",
     {"speaker": "Erastus Ethekon", "verb": "according to"}),
    ("“We are ready for the polls,” said Ethekon.",
     {"speaker": "Erastus Ethekon", "how": "named"}),
    ("“Investigations into the matter are ongoing,” the DCI said in a statement.",
     {"speaker": "Directorate of Criminal Investigations", "how": "named"}),
    ("“We have done our part. Parliament must now act,” Mbadi told reporters.",
     {"speaker": "John Mbadi", "verb": "tell"}),
    ("“Nitapita asubuhi na mapema sana,” Mosiria said.",
     {"speaker": "Geoffrey Mosiria", "language": "other"}),
    ("The crowd chanted “Ruto must go home now” as police watched.",
     {"how": "unattributed"}),
    ("Ruto pledged a ‘modern’ police force for the country.", None),
    # a bare title stands for whoever holds it in the story
    ("Deputy President Kithure Kindiki toured Embu on Monday. “We will vet all "
     "alcohol manufacturers afresh,” the DP said.",
     {"speaker": "Kithure Kindiki", "how": "pronoun"}),
    # "he" is the person who acted, not the one only mentioned: this once came
    # out as the late Raila Odinga
    ("President William Ruto commissioned the mausoleum of the late Raila Odinga in "
     "Bondo. “The site will now be run by the National Museums of Kenya,” he said.",
     {"speaker": "William Ruto", "how": "pronoun"}),
    # the real case: spaCy read "CS Wendot" as an organisation, so "she" became Raila
    ("CS Wendot noted that the agency will manage the site to safeguard Raila's "
     "contributions. “The completion of the mausoleum marks an important milestone for "
     "the country,” she added.",
     {"speaker": "Wendot", "how": "pronoun"}),
    # a quote paragraph with no attribution continues the last speaker
    ("Interior CS Kipchumba Murkomen addressed residents in Eldoret on Monday. "
     "“We will not allow cattle rustlers to terrorise residents,” Murkomen said. "
     "“Additional officers have already been deployed to the affected areas.”",
     {"speaker": "Kipchumba Murkomen", "how": "named"}),
    # the name of a thing in quote marks is not speech
    ("The world marks the day under the theme “Adequate Housing for All” this week.",
     None),
]
# the second quote of a passage, checked separately: it has no attribution of its own
CONTINUED = ("Interior CS Kipchumba Murkomen addressed residents in Eldoret on Monday. "
             "“We will not allow cattle rustlers to terrorise residents,” Murkomen said. "
             "“Additional officers have already been deployed to the affected areas.”")


def version(source, quote, speaker="Kithure Kindiki", ident="kithure-kindiki"):
    return {"source": source, "quote": quote, "speaker": speaker, "speaker_id": ident,
            "verb": "say", "how": "named", "language": "en"}


# (name, quotes from several outlets, {source: expected relation})
ALIGN = [
    ("the same remark, quoted alike",
     [version("KBC", "We will not allow anyone to intimidate voters during the elections."),
      version("Nation Africa", "We will not allow anyone to intimidate voters during the elections.")],
     {"Nation Africa": "same"}),
    ("one outlet trims the remark",
     [version("KBC", "We will not allow anyone to intimidate voters during the elections, "
                     "and those who try will face the full force of the law."),
      version("Capital FM", "We will not allow anyone to intimidate voters during the elections.")],
     {"Capital FM": "says less"}),
    ("two different remarks are not lined up",
     [version("KBC", "We will not allow anyone to intimidate voters during the elections."),
      version("People Daily", "Farmers in Meru will receive subsidised fertiliser from next week.")],
     {}),
    # Capital FM and Nairobi Wire named the same CS by different surnames
    ("the same words under two names for one speaker",
     [version("Capital FM", "A mausoleum is not merely a structure. It is a repository of "
                            "memory, history and identity,", "Cheptumo", None),
      version("Nairobi Wire", "A mausoleum is not merely a structure. It is a repository of "
                              "memory, history, and identity,", "Wendot", None)],
     {"Nairobi Wire": "same"}),
    ("an unattributed quote joins whoever another outlet credited",
     [version("Capital FM", "We do not have an Ebola outbreak in Kenya, what we have is an "
                            "imported case.", "Aden Duale", "aden-duale"),
      dict(version("KBC", "We do not have an Ebola outbreak in Kenya, what we have is an "
                          "imported case.", None, None), how="unattributed")],
     {"KBC": "same"}),
]


def run():
    passed = total = 0
    for text, wanted in EXTRACT:
        found = extract_quotes(text)
        if wanted is None:
            ok, detail = not found, f"got {found}"
        else:
            got = found[0] if found else {}
            wrong = {k: got.get(k) for k, v in wanted.items() if got.get(k) != v}
            ok, detail = bool(found) and not wrong, f"got {wrong or 'no quote'}"
        passed += ok
        total += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {text[:70]:<70} {'' if ok else detail}")
    found = extract_quotes(CONTINUED)
    second = found[1] if len(found) > 1 else {}
    ok = second.get("speaker") == "Kipchumba Murkomen" and second.get("how") == "continued"
    passed += ok
    total += 1
    print(f"  {'PASS' if ok else 'FAIL'}  {'an unattributed quote continues the last speaker':<70} "
          f"{'' if ok else f'got {second}'}")
    for name, quotes, wanted in ALIGN:
        remarks = align_quotes(quotes)
        lined = {v["source"]: v["relation"] for r in remarks for v in r["versions"]
                 if v["relation"] != "first"}
        ok = lined == wanted
        passed += ok
        total += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<70} {'' if ok else f'got {lined}'}")
    return passed, total


if __name__ == "__main__":
    passed, total = run()
    print(f"\n{passed}/{total} quote cases")
    sys.exit(0 if passed == total else 1)
