"""Teach spaCy Kenyan names, institutions and places.

spaCy's small English model was trained on American news. On this corpus it
tagged Kenyan names and institutions correctly in 26% of headlines and 74% of
snippet sentences: "Ruto" was missed in 38 of 40 headlines, "Kindiki" called an
organisation in 36 of 40, "IEBC" missed in 33 of 38. Every feature built on its
entities inherited that - framing compares only the people it finds, and the
figure digest keeps places apart only when it recognises them.

spaCy's own model runs first. Two components then correct it:

  kenyan_list      finds the names in backend/data/kenya_entities.json, each
                   with an id, so "Riggy G", "Gachagua" and "Rigathi Gachagua"
                   resolve to one person
  kenyan_entities  reconciles: a listed name replaces whatever spaCy said about
                   the same words, except where spaCy's span is longer for a
                   reason ("Isiolo County", "Langata Cemetery"); then a name
                   nobody listed is recognised by the title in front of it -
                   "CS Mugaa", "MP Wandeto", "Governor Kahiga"

They ran ahead of spaCy's model at first, and took words it would have read
better: "Narok Governor Patrick ole Ntutu" came out as "Patrick", and
"Langata Cemetery" as the place "Langata".

The title rule is skipped on Title Case text, where every word is capitalised
and "Governor Begins Probe" would yield a person called "Begins Probe".
backend.nlp.truecase restores a headline's case first where that matters.
"""
import json
from functools import lru_cache

import spacy
from spacy.language import Language
from spacy.matcher import Matcher
from spacy.tokens import Span

from backend.config import KENYAN_ENTITIES_PATH, NAME_TITLES, SPACY_MODEL
from backend.nlp.truecase import is_title_case

SECTION_LABELS = {
    "people": "PERSON",
    "organisations": "ORG",
    "places": "GPE",
    "regions": "LOC",
    "facilities": "FAC",
    "groups": "NORP",
}
SPANS_KEY = "kenyan_list"
# a titled name is at most this many words: "Patrick ole Ntutu", "Amason Jeffah Kingi"
MAX_TITLED_NAME_TOKENS = 4
# Honorifics matched only as written: "DR Congo" is not a doctor called Congo.
CASED_TITLES = {"dr": ("Dr",), "prof": ("Prof",), "hon": ("Hon",), "rev": ("Rev",)}
# Capitalised words that follow a title without being a name: "Justice Ministry",
# "Governor Aspirants", "Senator Elect".
NOT_NAMES = {
    "ministry", "department", "committee", "court", "commission", "council", "party",
    "house", "office", "service", "authority", "board", "fund", "bank", "university",
    "school", "hospital", "county", "government", "assembly", "senate", "police",
    "nominee", "nominees", "aspirant", "aspirants", "candidate", "candidates", "elect",
    "emeritus", "general", "secretary", "state", "national", "republic", "congo",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday",
}
# Words that make spaCy's longer span the better one: "Isiolo County" and
# "Langata Cemetery" are more specific than the listed place inside them.
PLACE_SUFFIXES = {
    "county", "sub-county", "ward", "constituency", "town", "city", "estate", "road",
    "street", "avenue", "highway", "market", "cemetery", "stadium", "hospital",
    "school", "college", "university", "church", "mosque", "airport", "port", "prison",
    "station", "bridge", "dam", "forest", "park", "gardens", "refinery", "region",
    "gymnasium", "hall", "grounds", "centre", "center", "arena", "showground", "camp",
}
# Particles that sit lowercase inside Kenyan names: Patrick ole Ntutu,
# Daniel arap Moi, Waruguru wa Ngugi.
NAME_PARTICLES = {"ole", "arap", "wa", "bin", "binti"}
_TITLE_WORDS = {word for title in NAME_TITLES for word in title.split()}
_BARE_TITLES = _TITLE_WORDS | {"lady", "mr", "mrs", "ms", "madam", "sir", "mheshimiwa"}


@lru_cache(maxsize=1)
def load_entities(path=KENYAN_ENTITIES_PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _entries(section, data):
    """Entries as dicts, whether the file lists a bare name or a full record."""
    for entry in data.get(section, []):
        yield {"name": entry} if isinstance(entry, str) else entry


def spellings(name):
    """Matiang'i as Kenyan outlets print it: straight, curly, or with no apostrophe."""
    forms = {name}
    if "'" in name or "’" in name:
        forms |= {name.replace("’", "'"), name.replace("'", "’"),
                  name.replace("’", "").replace("'", "")}
    return forms


def ruler_patterns(nlp, data=None):
    data = data or load_entities()
    patterns = []
    for section, label in SECTION_LABELS.items():
        for entry in _entries(section, data):
            for name in [entry["name"], *entry.get("aliases", [])]:
                for form in spellings(name):
                    if entry.get("case_sensitive"):
                        pattern = [{"ORTH": token.text} for token in nlp.make_doc(form)]
                    else:
                        pattern = form
                    item = {"label": label, "pattern": pattern}
                    if entry.get("id"):
                        item["id"] = entry["id"]
                    patterns.append(item)
    # tagged as people but never resolved to one: see the file's notes
    for name in data.get("names_without_identity", []):
        for form in spellings(name):
            patterns.append({"label": "PERSON", "pattern": form})
    return patterns


@Language.factory("kenyan_entities")
def make_kenyan_entities(nlp, name):
    return KenyanEntities(nlp)


class KenyanEntities:
    """Merge the listed names and titled names into spaCy's own entities."""

    def __init__(self, nlp):
        self.matcher = Matcher(nlp.vocab)
        for title in NAME_TITLES:
            if title in CASED_TITLES:
                words = [{"ORTH": {"IN": list(CASED_TITLES[title])}}]
            else:
                words = [{"LOWER": word} for word in title.split()]
            # "Dr." and "Hon." are often written with a full stop
            self.matcher.add("TITLE", [words + [{"ORTH": ".", "OP": "?"}]])

    def __call__(self, doc):
        ents = list(doc.ents)
        for listed in spacy.util.filter_spans(doc.spans.get(SPANS_KEY, [])):
            clashes = [e for e in ents if e.start < listed.end and listed.start < e.end]
            better = next((e for e in clashes if _more_specific(e, listed)), None)
            if better is not None:
                label = better.label_
                if listed.label_ == "PERSON" and _longer_name(better, listed):
                    # spaCy found more of a person's name but may have called it
                    # a place: alone it read "Nderitu Gachagua" as a GPE
                    label = "PERSON"
                # "Abraham Kithure Kindiki": spaCy's full name, the list's identity -
                # only when every word is that person's. "Nderitu Gachagua", a late
                # Nyeri governor, is someone else.
                ident = better.id_ or (listed.id_ if _names_agree(better, listed.id_) else "")
                if (label, ident) != (better.label_, better.id_):
                    ents[ents.index(better)] = Span(doc, better.start, better.end,
                                                    label=label, span_id=ident)
                continue
            ents = [e for e in ents if e not in clashes]
            ents.append(Span(doc, listed.start, listed.end, label=listed.label_,
                             span_id=listed.id_))
        _set_ents(doc, sorted(ents, key=lambda e: e.start))
        return self._titled_names(doc)

    def _titled_names(self, doc):
        ents = list(doc.ents)
        for _, start, end in self.matcher(doc):
            if is_title_case(doc[start].sent.text):
                continue
            stop = _name_end(doc, end)
            if stop == end:
                continue
            clashes = [e for e in ents if e.start < stop and end < e.end]
            inside = all(end <= e.start and e.end <= stop for e in clashes)
            # spaCy's span swallowed the title too: "CS Wendot" as an organisation
            titled = all(start <= e.start and e.end <= stop and e.label_ != "PERSON"
                         for e in clashes)
            if clashes and titled:
                ents = [e for e in ents if e not in clashes]
                ents.append(Span(doc, end, stop, label="PERSON"))
            elif not clashes or (inside and all(e.label_ != "PERSON" for e in clashes)):
                # nothing there, or only wrong guesses about parts of it:
                # "Governor Irungu Kang'ata" had "Kang'ata" as an organisation
                ents = [e for e in ents if e not in clashes]
                ents.append(Span(doc, end, stop, label="PERSON"))
            elif (inside and len(clashes) == 1 and clashes[0].label_ == "PERSON"
                  and len(clashes[0]) < stop - end):
                # The title reads more of the name than anything else did. It keeps
                # a listed identity only if the extra words are that person's:
                # "late Nyeri Governor Nderitu Gachagua's son" is not Rigathi.
                person = clashes[0]
                ident = person.id_ if person.id_ and _names_agree(doc[end:stop], person.id_) else ""
                ents[ents.index(person)] = Span(doc, end, stop, label="PERSON", span_id=ident)
            elif len(clashes) == 1 and clashes[0].start == end and clashes[0].label_ != "PERSON":
                # spaCy found the name but called it something else; keep its extent
                wrong = clashes[0]
                ents[ents.index(wrong)] = Span(doc, wrong.start, wrong.end,
                                               label="PERSON", span_id=wrong.id_)
        # "Lady Justice ..." - spaCy took the title itself for a person
        ents = [e for e in ents if not (e.label_ == "PERSON"
                                        and all(t.lower_ in _BARE_TITLES for t in e))]
        _set_ents(doc, spacy.util.filter_spans(ents))
        return doc


def _set_ents(doc, ents):
    """doc.ents = ents, without stale identities.

    spaCy keeps an entity id on each word, and assigning new entities does not
    clear it: replacing "Gachagua" (Rigathi) with "Nderitu Gachagua" (no id)
    left Rigathi's id on the word "Gachagua", and the late governor was counted
    as him. Every word is cleared first; spans that carry an id set it again.
    """
    for token in doc:
        token.ent_id = 0
    doc.ents = ents


def _more_specific(theirs, listed):
    """spaCy's span contains the listed one and only adds detail to it.

    Two kinds of detail: a place-type word ("Isiolo County"), or more of the
    same person's name ("Abdi Hassan Guyo" around a listed "Guyo"). A title is
    not detail - "Deputy President Kindiki" gives way to the listed "Kindiki",
    so the title stays outside the name where it can be read separately.
    """
    if len(theirs) == len(listed):
        return False
    if not (theirs.start <= listed.start and listed.end <= theirs.end):
        return False
    extra = [t for t in theirs if t.i < listed.start or t.i >= listed.end]
    if all(t.lower_ in PLACE_SUFFIXES or t.lower_ == "the" for t in extra):
        return True
    return listed.label_ == "PERSON" and _longer_name(theirs, listed)


def _longer_name(theirs, listed):
    """spaCy's span is the listed name with more name words around it."""
    extra = [t for t in theirs if t.i < listed.start or t.i >= listed.end]
    return bool(extra) and all(_name_word(t) or t.lower_ in NAME_PARTICLES for t in extra)


def _names_agree(span, ident):
    """Whether every word of a longer name belongs to the listed person's names."""
    entry = people().get(ident)
    if entry is None:
        return False
    known = {word.lower() for name in [entry["name"], *entry.get("aliases", [])]
             for form in spellings(name) for word in form.split()}
    return all(t.lower_ in known or t.lower_ in NAME_PARTICLES
               for t in span if not t.is_punct)


def _name_end(doc, start):
    """Where a name that begins at start ends, taking particles in stride."""
    stop = start
    while stop < len(doc) and stop - start < MAX_TITLED_NAME_TOKENS:
        token = doc[stop]
        if _name_word(token):
            stop += 1
        elif (token.lower_ in NAME_PARTICLES and stop > start
              and stop + 1 < len(doc) and _name_word(doc[stop + 1])):
            stop += 1
        else:
            break
    return stop


def _name_word(token):
    return (_capitalised(token.text) and not token.is_stop and not token.like_num
            and token.lower_ not in _TITLE_WORDS and token.lower_ not in NOT_NAMES)


def _capitalised(word):
    """Capital first letter, lowercase after. str.istitle() rejects "Kang'ata",
    reading the letter after an apostrophe as the start of a new word."""
    letters = word.replace("’", "").replace("'", "").replace("-", "")
    return letters[:1].isupper() and letters[1:].islower()


def add_kenyan_entities(nlp):
    """Install both components after spaCy's entity model, which they correct."""
    finder = nlp.add_pipe("span_ruler", name=SPANS_KEY, after="ner",
                          config={"spans_key": SPANS_KEY, "phrase_matcher_attr": "LOWER",
                                  "annotate_ents": False})
    finder.add_patterns(ruler_patterns(nlp))
    nlp.add_pipe("kenyan_entities", after=SPANS_KEY)
    return nlp


def load_nlp(lemmas=False):
    """The project's spaCy pipeline. Lemmas are needed only to read verbs."""
    disabled = ["textcat"] if lemmas else ["lemmatizer", "textcat"]
    return add_kenyan_entities(spacy.load(SPACY_MODEL, disable=disabled))


@lru_cache(maxsize=1)
def people():
    """{id: entry} for every person the list can identify."""
    return {e["id"]: e for e in _entries("people", load_entities()) if e.get("id")}


@lru_cache(maxsize=1)
def listed_names():
    """{id: canonical name} for every listed entry with an id, people or not:
    "DCI" and "Directorate of Criminal Investigations" are one speaker."""
    data = load_entities()
    return {e["id"]: e["name"] for section in SECTION_LABELS
            for e in _entries(section, data) if e.get("id")}


def find_person(query):
    """The id for an id, name or alias a user typed, or None."""
    wanted = {form.lower() for form in spellings(query.strip())}
    for ident, entry in people().items():
        names = {ident, entry["name"], *entry.get("aliases", [])}
        if any(form.lower() in wanted for name in names for form in spellings(name)):
            return ident
    return None


def all_names(ident):
    """Every spelling of a person's name, for a quick text search before parsing."""
    entry = people()[ident]
    return sorted({form for name in [entry["name"], *entry.get("aliases", [])]
                   for form in spellings(name)}, key=len, reverse=True)
