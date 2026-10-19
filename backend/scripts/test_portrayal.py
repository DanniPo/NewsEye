"""Does portrayal read who speaks, who acts and who is acted on?

Each case is a headline or lede in the forms Kenyan outlets use, the person it
is checked for, and what must be recorded. Several are the mistakes the first
version made on live data: "Gachagua vs Uhuru: The battle for Mt Kenya" read
as Gachagua speaking, "joining Gachagua's DCP" as someone joining him, and
"Ipoa launches investigations into shooting at Kindiki meeting" would have
been Kindiki launching something.

    python -m backend.scripts.test_portrayal
"""
import sys

from backend.analysis.portrayal import CURLY_POSSESSIVE, mentions
from backend.nlp.entities import load_nlp
from backend.nlp.truecase import build_casing_lexicon, truecase
from backend.scripts.testkit import case, fields, report

# (text, person, expected fields of their first mention)
CASES = [
    ("Gachagua claims plot to arrest him ahead of rally",
     "rigathi-gachagua", {"role": "speaks", "verb": "claim", "family": "claimed"}),
    ("Ruto: We will not tolerate graft in Kilifi",
     "william-ruto", {"role": "speaks", "family": "quoted directly"}),
    ("Kalonzo: Uhuru was right to say Raila won",
     "uhuru-kenyatta", {"role": "spoken about", "by": "Kalonzo Musyoka"}),
    ("MPs slam Ruto over the housing levy",
     "william-ruto", {"role": "acted on", "verb": "slam", "by": "MPs"}),
    ("Ruku hits back at Gachagua over Kindiki coronation hat fall controversy",
     "rigathi-gachagua", {"role": "acted on", "verb": "hit back at", "by": "Ruku"}),
    ("Ipoa launches investigations into fatal shooting at Kindiki meeting in Nembure",
     "kithure-kindiki", {"role": "mentioned"}),
    ("Kindiki launches affordable housing project in Embu",
     "kithure-kindiki", {"role": "acts", "verb": "launch"}),
    ("Former Deputy President Rigathi Gachagua has accused the government of plotting chaos",
     "rigathi-gachagua", {"role": "speaks", "verb": "accuse", "title": "former deputy president"}),
    ("Waiguru rules out joining Gachagua’s DCP, cites Ngirici's treatment",
     "rigathi-gachagua", {"role": "mentioned"}),
    ("Gachagua was impeached by the Senate in October",
     "rigathi-gachagua", {"role": "acted on", "verb": "impeach"}),
    ("According to Interior CS Kipchumba Murkomen, the operation will continue",
     "kipchumba-murkomen", {"role": "speaks", "verb": "according to", "title": "interior cs"}),
    ("DP Kindiki: No more importation of rice until locally produced crop is sold",
     "kithure-kindiki", {"role": "speaks", "family": "quoted directly", "title": "dp"}),
    ("Atwoli tells Gachagua to stop invoking his name for political relevance",
     "rigathi-gachagua", {"role": "acted on", "verb": "tell", "by": "Atwoli"}),
    ("Uhuru was right, says Kalonzo",
     "uhuru-kenyatta", {"role": "described"}),
    # "Speaker to Addressee: words" - Gachagua is inside Wanga's words
    ("Wanga to Kalonzo: We loved you until you joined Gachagua",
     "rigathi-gachagua", {"role": "spoken about", "by": "Gladys Wanga"}),
    # found by the held-out test, 19 Oct: reported speech read as acting
    ("Wiper Patriotic Front leader Kalonzo Musyoka has reaffirmed that the journey to "
     "Canaan remains on course",
     "kalonzo-musyoka", {"role": "speaks", "verb": "reaffirm"}),
    ("Agriculture Cabinet Secretary Mutahi Kagwe has called for reforms in the global "
     "coffee industry",
     "mutahi-kagwe", {"role": "speaks", "verb": "call for", "family": "urged or warned"}),
    # a title in front of the name: read as named in passing until 19 Oct
    ("Nairobi Senator Edwin Sifuna has said his immediate priority is to reorganise his "
     "political party",
     "edwin-sifuna", {"role": "speaks", "verb": "say"}),
    ("Lang’ata MP Felix Jalang’o and East African Legislative Assembly (EALA) MP Winnie "
     "Odinga are preparing for a political contest",
     "winnie-odinga", {"role": "acts", "verb": "prepare"}),
]
# an opening line cut at 150 characters mid-clause: every mention, in order. The
# second "Oburu" was read as acting, with "have" as its verb, until 19 Oct.
CUT_OFF = [
    ("Orange Democratic Movement (ODM) party leader Oburu Oginga has explained why he will "
     "not be attending public events in the immediate future. Oburu has",
     "oburu-oginga", ["speaks", "mentioned"]),
]
# must not be read as the person speaking
NOT_SPEAKING = [
    ("Gachagua vs Uhuru: The battle for Mt Kenya after Ruto", "rigathi-gachagua"),
    ("2027: How court puts IEBC under tighter rules on Ruto's poll results", "william-ruto"),
]
# Title Case headlines go through truecasing first, as in portray()
TITLE_CASE = [
    ("Kioni Warns Gachagua: Stop ‘Ruining’ The United Opposition",
     "rigathi-gachagua", {"role": "acted on", "verb": "warn"}),
]
LEXICON_SOURCE = [
    "He warns that leaders must stop ruining the party and the coalition.",
    "Critics say the plan will stop ruining the economy, he warns.",
]


def first_mention(nlp, text, person):
    found = mentions(nlp(CURLY_POSSESSIVE.sub("'", text)), person)
    return found[0] if found else None


def check(text, person, got, wanted):
    """The case record for one mention against the fields it must have."""
    if got is None:
        return case(text, f"{person}: {fields(wanted)}", f"{person}: not found", False)
    actual = {key: got.get(key) for key in wanted}
    return case(text, f"{person}: {fields(wanted)}", f"{person}: {fields(actual)}",
                actual == wanted)


def results():
    nlp = load_nlp(lemmas=True)
    lexicon = build_casing_lexicon(LEXICON_SOURCE, min_count=1)
    rows = [check(text, person, first_mention(nlp, text, person), wanted)
            for text, person, wanted in CASES]
    for text, person in NOT_SPEAKING:
        got = first_mention(nlp, text, person)
        role = got["role"] if got else "not found"
        rows.append(case(text, f"{person}: any role but speaks", f"{person}: role {role}",
                         got is not None and role != "speaks"))
    rows += [check(text, person, first_mention(nlp, truecase(text, lexicon), person), wanted)
             for text, person, wanted in TITLE_CASE]
    for text, person, wanted in CUT_OFF:
        got = [m["role"] for m in mentions(nlp(CURLY_POSSESSIVE.sub("'", text)), person)]
        rows.append(case(text, f"{person}: {', '.join(wanted)}",
                         f"{person}: {', '.join(got) or 'not found'}", got == wanted))
    return rows


if __name__ == "__main__":
    sys.exit(report(results(), "portrayal cases"))
