"""Direct quotes in a story, who said them, and how each outlet quoted them.

Runs in the active tier on the article text it fetches and then discards. It
keeps only the quoted words and the attribution - no more of an article than
the claims keep.

Finding the speaker, in order of trust:

  named        a reporting verb outside the quote whose subject is a name:
               '"We are ready," IEBC chair Erastus Ethekon said'
  pronoun      the subject is "he", "she", "I" or "we", or a bare title ("the
               DP said"): the nearest person before it who is the subject of a
               sentence - someone who said or did something, not a name in
               passing. Taking the nearest name of any kind credited the late
               Raila Odinga with a quote about his own mausoleum.
  described    the subject is a description: "the ministry said", "police said"
  continued    no attribution of its own: the speaker of the quote or reporting
               verb just before it, as news paragraphs run on
  unattributed nothing says who spoke

Then each speaker's quotes are lined up across outlets. Two quotes are the same
remark when their wording is close (QUOTE_MATCH_SIMILARITY); NLI read both
ways then says how each outlet's version relates to the first:

  same              the two versions imply each other
  says more         this version contains the other and adds to it
  says less         this version is contained in the other
  worded differently  neither contains the other: read both
  not compared      not in English; the NLI model reads English only

Near-identical words are one remark even when outlets name the speaker
differently: Capital FM's "Cheptumo" and Nairobi Wire's "Wendot" quoted the
same CS saying "A mausoleum is not merely a structure".

None of these says anyone was misquoted. Outlets trim long remarks for space
and translate Swahili ones; the reader sees the versions side by side.
"""
import re
from collections import defaultdict
from functools import lru_cache

from backend.analysis.portrayal import (
    CURLY_POSSESSIVE,
    TITLE_WORDS,
    family_of,
    title_of,
    verb_phrase,
)
from backend.config import QUOTE_MATCH_SIMILARITY, QUOTE_MAX_CHARS, QUOTE_MIN_WORDS
from backend.nlp.entities import listed_names, load_nlp

DOUBLE = re.compile(r"“([^“”]{2,}?)”|\"([^\"]{2,}?)\"")
# single quotes double as apostrophes: only one that opens a word and closes one
SINGLE = re.compile(r"(?:(?<=\s)|^)‘([^‘’]{2,}?)’(?=[\s,.:;!?]|$)")
# "I" and "we" outside quote marks are a speaker's words running on past a
# paragraph break, where outlets drop the closing mark
PRONOUNS = {"he", "she", "i", "we"}
# a bare title stands for whoever last held it in the story: "the DP said"
TITLE_EXPANSIONS = {"dp": "deputy president", "cs": "cabinet secretary",
                    "ps": "principal secretary", "cj": "chief justice",
                    "ig": "inspector general", "ag": "attorney general"}
# an attribution sentence after the quote is short: '"...," he said on Tuesday.'
MAX_AFTER_TOKENS = 12
# how far back to look for the person a pronoun or title stands for
LOOKBACK_SENTENCES = 3
# below this share of English function words, a quote is taken to be in another language
ENGLISH_SHARE = 0.15
# the same words from two outlets are one remark whoever they credit
SAME_WORDS = 0.9
# a quote paragraph without attribution continues a speaker this many sentences back
CONTINUE_SENTENCES = 2
# a quoted phrase this short in Title Case names a thing: a theme, a book, a slogan
TITLE_QUOTE_WORDS = 8
MAX_TEXT_CHARS = 20000


@lru_cache(maxsize=1)
def _nlp():
    return load_nlp(lemmas=True)


def _quote_spans(text):
    for match in DOUBLE.finditer(text):
        yield match.start(), match.end(), (match.group(1) or match.group(2)).strip()
    for match in SINGLE.finditer(text):
        yield match.start(), match.end(), match.group(1).strip()


def _language(quote, nlp):
    words = re.findall(r"[A-Za-z']+", quote.lower())
    if len(words) < QUOTE_MIN_WORDS:
        return "en"
    english = sum(1 for w in words if w in nlp.Defaults.stop_words)
    return "en" if english / len(words) >= ENGLISH_SHARE else "other"


def _entity_at(doc, token):
    return next((e for e in doc.ents if e.start <= token.i < e.end), None)


def _name_of(entity):
    return listed_names().get(entity.ent_id_, entity.text), (entity.ent_id_ or None)


def _title_words(words):
    """Title words in full, so "DP" and "Deputy President" compare equal."""
    expanded = set()
    for word in words:
        expanded.update(TITLE_EXPANSIONS.get(word, word).split())
    return expanded - {"former", "the", "of"}


def _bare_title(subject):
    """The title words, if the subject is a title and nothing else: "the DP"."""
    words = [t.lower_ for t in subject.subtree if not t.is_punct and t.dep_ != "det"]
    if words and all(w in TITLE_WORDS for w in words):
        return _title_words(words)
    return None


def _resolve_back(doc, subject, inside, titles=None):
    """The nearest person before subject that it stands for, or None.

    People who are the subject of a sentence first - someone who spoke or
    acted - then anyone named. With titles, only a person given those titles.
    """
    sents = list(doc.sents)
    here = next(i for i, s in enumerate(sents) if s.start <= subject.i < s.end)
    first = sents[max(0, here - LOOKBACK_SENTENCES)].start
    before = [e for e in sorted(doc.ents, key=lambda e: -e.start)
              if e.label_ == "PERSON" and first <= e.start < subject.i
              and not inside(e.start_char)]
    if titles is not None:
        before = [e for e in before
                  if _title_words(title_of(e).lower().split()) == titles]
    # someone who just said something, then someone who did something, then
    # anyone named: "CS Wendot noted..." comes before the late Raila Odinga,
    # who is only mentioned
    speaking = [e for e in before if e.root.dep_ == "nsubj"
                and family_of(verb_phrase(e.root.head))]
    acting = [e for e in before if e.root.dep_ in ("nsubj", "nsubjpass")]
    found = (speaking or acting or before or [None])[0]
    return _name_of(found) if found is not None else (None, None)


def _speaker(doc, subject, inside):
    """(name, id, how) for the subject of a reporting verb.

    A person inside the subject's phrase wins over the body they belong to:
    "IEBC chairperson Erastus Ethekon" is Ethekon speaking, not the IEBC.
    """
    titles = _bare_title(subject)
    if titles:
        name, ident = _resolve_back(doc, subject, inside, titles)
        return (name, ident, "pronoun") if name else (None, None, "unattributed")
    if subject.lower_ in PRONOUNS:
        name, ident = _resolve_back(doc, subject, inside)
        return (name, ident, "pronoun") if name else (None, None, "unattributed")
    found = {e for t in subject.subtree
             if (e := _entity_at(doc, t)) is not None and not inside(e.start_char)}
    for label in ("PERSON", "ORG", "NORP"):
        entity = next((e for e in sorted(found, key=lambda e: e.start) if e.label_ == label), None)
        if entity is not None:
            name, ident = _name_of(entity)
            return name, ident, "named"
    words = [t.text for t in subject.subtree if not t.is_punct][:5]
    return (" ".join(words) or None), None, "described"


def _attribution(doc, start, end, inside):
    """(name, id, verb, how) for the quote between characters start and end."""
    sents = [s for s in doc.sents if s.start_char < end and s.end_char > start]
    after = next((s for s in doc.sents if s.start_char >= end), None)
    if after is not None and len(after) <= MAX_AFTER_TOKENS:
        sents.append(after)
    before = next((s for s in reversed(list(doc.sents)) if s.end_char <= start), None)
    if before is not None and before.text.rstrip().endswith(":"):
        sents.insert(0, before)
    for sent in sents:
        for token in sent:
            if inside(token.idx) or token.pos_ not in ("VERB", "AUX"):
                continue
            if token.lower_ == "according":
                # the whole phrase, not only the object of "to": spaCy attached
                # "IEBC" to "to" and "Ethekon" to "According" in "According to
                # IEBC chairperson Erastus Ethekon"
                name, ident, how = _speaker(doc, token, inside)
                if name:
                    return name, ident, "according to", how
                continue
            phrase = verb_phrase(token)
            if not family_of(phrase):
                continue
            subject = next((c for c in token.children if c.dep_ == "nsubj"), None)
            if subject is None or inside(subject.idx):
                continue
            name, ident, how = _speaker(doc, subject, inside)
            if name:
                return name, ident, phrase, how
    return None, None, None, "unattributed"


def extract_quotes(text):
    """Every direct quote of QUOTE_MIN_WORDS or more, with who said it."""
    if not text:
        return []
    nlp = _nlp()
    doc = nlp(CURLY_POSSESSIVE.sub("'", text[:MAX_TEXT_CHARS]))
    spans = sorted({(s, e, q) for s, e, q in _quote_spans(doc.text)})

    def inside(char):
        return any(s <= char < e for s, e, _ in spans)

    quotes, attributed = [], []
    for start, end, quote in spans:
        if len(quote.split()) < QUOTE_MIN_WORDS:
            continue   # scare quotes and nicknames: 'modern', "Wantam"
        if _names_a_thing(quote):
            continue   # the name of a thing, not speech: "Adequate Housing for All"
        name, ident, verb, how = _attribution(doc, start, end, inside)
        if name is None:
            name, ident = _continued(doc, start, attributed, inside)
            how = "continued" if name else how
        elif how != "described":
            attributed.append((end, name, ident))
        quotes.append({
            "quote": quote[:QUOTE_MAX_CHARS],
            "speaker": name, "speaker_id": ident, "verb": verb, "how": how,
            "language": _language(quote, nlp),
        })
    return quotes


def _names_a_thing(quote):
    """A short phrase with every longer word capitalised: a theme, a title, a slogan.

    truecase.is_title_case judges headlines and skips their first word, which
    leaves a four-word theme with nothing to judge it by.
    """
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", quote)
    longer = [w for w in words if len(w) > 3]
    return (len(words) <= TITLE_QUOTE_WORDS and len(longer) >= 2
            and all(w[0].isupper() for w in longer))


def _continued(doc, start, attributed, inside):
    """The speaker an unattributed quote continues, by newsroom convention.

    A quote paragraph with no "he said" belongs to the last speaker: the one
    attributed in a quote just before, or the subject of a reporting verb in
    the sentences leading up to it ("CS Wendot noted that the agency will...").
    """
    sents = list(doc.sents)
    here = next((i for i, s in enumerate(sents) if s.start_char <= start < s.end_char), None)
    if here is None:
        return None, None
    floor = sents[max(0, here - CONTINUE_SENTENCES)].start_char
    nearest, found = floor, (None, None)
    for end, name, ident in attributed:
        if floor <= end <= start and end >= nearest:
            nearest, found = end, (name, ident)
    for sent in sents[max(0, here - CONTINUE_SENTENCES):here + 1]:
        for token in sent:
            if (token.idx >= start or inside(token.idx) or token.pos_ not in ("VERB", "AUX")
                    or not family_of(verb_phrase(token))):
                continue
            subject = next((c for c in token.children if c.dep_ == "nsubj"), None)
            if subject is None or inside(subject.idx) or subject.idx < nearest:
                continue
            name, ident, how = _speaker(doc, subject, inside)
            if name and how != "described":
                nearest, found = subject.idx, (name, ident)
    return found


def _speaker_keys(quotes, vectors):
    """One key per speaker, joining the names outlets used for the same person.

    Speakers are joined when two outlets quote near-identical words under
    different names - "Cheptumo" and "Wendot" - and an unattributed quote joins
    whoever another outlet credited the same words to.
    """
    parent = {}

    def find(key):
        while parent.setdefault(key, key) != key:
            key = parent[key]
        return key

    keys = []
    for i, quote in enumerate(quotes):
        own = quote["speaker_id"] or (quote["speaker"] or "").lower()
        keys.append(own or f"#unattributed-{i}")
    similar = vectors @ vectors.T
    for i in range(len(quotes)):
        for j in range(i + 1, len(quotes)):
            if similar[i, j] >= SAME_WORDS and quotes[i]["source"] != quotes[j]["source"]:
                parent[find(keys[j])] = find(keys[i])
    return [find(k) for k in keys]


def align_quotes(quotes):
    """Each speaker's quotes, grouped into remarks across outlets.

    quotes carry "source" as well as the fields extract_quotes gives them.
    Returns one record per remark, the first version first.
    """
    from backend.nlp.embeddings import model
    from backend.nlp.nli import relations

    if not quotes:
        return []
    vectors = model.encode([q["quote"] for q in quotes], normalize_embeddings=True)
    by_speaker = defaultdict(list)
    for i, key in enumerate(_speaker_keys(quotes, vectors)):
        by_speaker[key].append(i)

    remarks = []
    for said in by_speaker.values():
        # an attributed version leads, so the remark carries a speaker
        said.sort(key=lambda i: quotes[i]["speaker"] is None)
        unassigned = list(said)
        while unassigned:
            seed = unassigned.pop(0)
            outlets = {quotes[seed]["source"]}
            members = []
            for other in list(unassigned):
                if (float(vectors[other] @ vectors[seed]) >= QUOTE_MATCH_SIMILARITY
                        and quotes[other]["source"] not in outlets):
                    members.append(other)
                    outlets.add(quotes[other]["source"])
                    unassigned.remove(other)
            first = quotes[seed]
            english = [m for m in members if quotes[m]["language"] == first["language"] == "en"]
            judged = dict(zip(english, relations([(first["quote"], quotes[m]["quote"])
                                                  for m in english]), strict=True))
            versions = [dict(first, relation="first")]
            for m in members:
                relation = ("not compared" if m not in judged else
                            {"same": "same", "first_more": "says less",
                             "second_more": "says more",
                             "different": "worded differently"}[judged[m][0]])
                versions.append(dict(quotes[m], relation=relation))
            remarks.append({"speaker": first["speaker"], "speaker_id": first["speaker_id"],
                            "outlets": len(outlets), "versions": versions})
    remarks.sort(key=lambda r: (-r["outlets"], r["speaker"] or ""))
    return remarks
