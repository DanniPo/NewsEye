"""Name what a story is about, in the words its own headlines used.

Shown on the story page so the reader knows which story they are looking at.
Extractive: the phrase is taken from the headlines, never generated, and the
only model involved is spaCy's parser.
"""
import re
from collections import Counter

from backend.analysis.claims import get_nlp
from backend.config import CORPUS_UNIVERSAL_TERMS

# longer than this and the "phrase" is really a clause dragged in by the parser
SUBJECT_MAX_TOKENS = 6

_KEYWORD_STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "says", "said"}
_LEADING_DET = re.compile(r"^(?:the|a|an)\s+", re.I)


def _clean(phrase):
    phrase = _LEADING_DET.sub("", (phrase or "").strip())
    return phrase.strip(" .,:;-|—").strip()


def _keyword_subject(titles):
    """Frequency-ranked keywords - the fallback for titles with no noun chunks."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", " ".join(titles).lower())
    counts = Counter(w for w in words if w not in _KEYWORD_STOPWORDS)
    terms = sorted(counts, key=lambda word: (-counts[word], word))[:6]
    return " ".join(terms) or "the story covered by these articles"


def _singular(word):
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def derive_subject(titles):
    """The phrase that names this cluster's story.

    Ranking loose keywords produced "foreign directive investment traders moves
    shape" - word order gone, and nothing that reads as a subject.

    The anchor is the head noun that (a) recurs across the cluster's titles and
    (b) attracts the most modifiers. Both halves matter. Frequency alone picks
    "Kenya" or "Ruto", which every title in a Kenyan politics cluster mentions
    and which therefore identifies the cluster rather than the story. A head
    that people keep qualifying - "Ruto's foreign trader directive" - is the one
    the coverage is actually about.
    """
    if not titles:
        return "the story covered by these articles"

    heads = {}
    for index, doc in enumerate(get_nlp().pipe([t for t in titles if t])):
        for chunk in doc.noun_chunks:
            if chunk.root.pos_ == "PRON":
                continue
            head = _singular(chunk.root.lower_)
            if len(head) < 3 or head in _KEYWORD_STOPWORDS:
                continue
            # "Kenya" heads more titles than the actual story does, and the
            # widest phrase ending in it was a sponsor's name
            if head in CORPUS_UNIVERSAL_TERMS:
                continue
            entry = heads.setdefault(head, {"titles": set(), "forms": []})
            entry["titles"].add(index)
            entry["forms"].append(chunk)

    if not heads:
        return _keyword_subject(titles)

    def widest(entry):
        usable = [len(c) for c in entry["forms"] if len(c) <= SUBJECT_MAX_TOKENS]
        return max(usable) if usable else 1

    # recurrence times phrase width, not one then the other: "Ruto" heads eight
    # titles but never takes a modifier (8 x 1), while "directive" heads four and
    # pulls three words with it (4 x 4). The second is the story.
    def rank(item):
        _, entry = item
        return len(entry["titles"]) * widest(entry)

    # a head only one title uses is that outlet's phrasing, not the cluster's
    recurring = {h: e for h, e in heads.items() if len(e["titles"]) >= 2}
    best_head, entry = max((recurring or heads).items(), key=rank)
    forms = [c for c in entry["forms"] if len(c) <= SUBJECT_MAX_TOKENS]
    if not forms:
        return best_head

    # the fullest phrasing of that head: "Ruto's foreign trader directive"
    best = max(forms, key=lambda c: (len(c), -c.start))
    return _clean(best.text) or best_head
