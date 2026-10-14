"""Put Title Case headlines back into sentence case before parsing.

spaCy's small English model leans on capital letters to find names, and many
outlets capitalise every word of a headline. On this corpus it tagged Kenyan
names and institutions correctly in 26% of headlines against 74% of snippets,
and read "Uhuru Says Raila Won" as a person called "Raila Won".

The fix needs no model. Snippets are written in sentence case, so they show how
each word is normally written: "says" is lowercase mid-sentence, "Raila" never
is. A Title Case headline is rewritten word by word to its usual form, and any
word the snippets have not settled stays as it is.
"""
import re
from collections import Counter

WORD = re.compile(r"[A-Za-z][A-Za-z’'\-]*")
# Small words that only Title Case capitalises. Names are capitalised in any
# style, so counting capitals alone mistook "CS Mugaa and MP Wandeto toured
# Nyeri on Monday" for a headline in Title Case.
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "but", "nor", "of", "in", "on", "at", "to", "for",
    "with", "into", "onto", "over", "after", "from", "as", "by", "about", "amid",
    "against", "before", "between", "during", "under", "up", "out", "off", "is",
    "are", "was", "were", "be", "will", "his", "her", "their", "its", "this", "that",
    "who", "what", "why", "how", "not", "no", "than", "via", "per",
}
# a capital straight after one of these starts a quote or a clause, in any style
FRESH_START = set(":“‘\"'.?!—-(")


def build_casing_lexicon(sentences, min_count=2):
    """{lowercase word: usual written form}, learned from sentence-case text.

    Sentence-initial words are skipped: every word is capitalised there, so
    they say nothing about how the word is normally written.
    """
    seen = {}
    for sentence in sentences:
        for match in list(WORD.finditer(sentence or ""))[1:]:
            word = match.group()
            if word.isupper():
                continue
            seen.setdefault(word.lower(), Counter())[word] += 1
    lexicon = {}
    for lower, forms in seen.items():
        form, count = forms.most_common(1)[0]
        if count >= min_count:
            lexicon[lower] = form
    return lexicon


def is_title_case(text):
    """True when capitals mark the style of the headline, not names.

    Two signs, either enough. A capitalised function word ("Into", "With"),
    which sentence case never writes. Or no ordinary longer word left in
    lowercase: some outlets keep "on" and "of" small in Title Case, but none
    writes "toured" or "declares" small, while a sentence always has some.
    """
    if not text:
        return False
    words = []
    for match in list(WORD.finditer(text))[1:]:
        before = text[:match.start()].rstrip()
        if before and before[-1] in FRESH_START:
            continue
        words.append(match.group())
    if any(w[0].isupper() and w.lower() in FUNCTION_WORDS for w in words):
        return True
    content = [w for w in words if len(w) > 3 and w.lower() not in FUNCTION_WORDS]
    return len(content) >= 2 and all(w[0].isupper() for w in content)


def truecase(text, lexicon):
    """The headline in sentence case, or unchanged if it already is."""
    if not text or not is_title_case(text):
        return text
    first = True

    def fix(match):
        nonlocal first
        word = match.group()
        if first:
            first = False
            return word
        if word.isupper() and len(word) > 1:   # acronyms: IEBC, KRA, DCI
            return word
        return lexicon.get(word.lower(), word)

    return WORD.sub(fix, text)
