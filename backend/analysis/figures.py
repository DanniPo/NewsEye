"""Read the numbers out of a sentence and label what each one is.

This module never compares figures or decides which one is right. It turns
"At least five people were killed in the Gotu ambush" into a value (5) with the
labels a reader needs to interpret it: what is being counted (people), what
kind of casualty count it is (dead), whether it is a running total, which place
the sentence is about, and which currency a sum is in.

analysis.digest uses those labels to decide which figures to show next to each
other and to annotate them on the page. The reader draws the conclusions.
"""
import re
from collections import Counter

# a subject word used by more than this share of a cluster's claims describes
# the whole story, so it says nothing about any one figure
SUBJECT_DF_LIMIT = 0.25

SCALES = {
    "hundred": 1e2, "thousand": 1e3, "k": 1e3,
    "million": 1e6, "m": 1e6, "mn": 1e6,
    "billion": 1e9, "bn": 1e9, "b": 1e9,
    "trillion": 1e12, "tn": 1e12,
}

# News style spells out numbers under ten, so "five people were killed" would
# otherwise carry no figure at all while "12 people were killed" does.
NUMBER_WORDS = {
    # "one" is left out on purpose: in news prose it is almost always "one of
    # the", "no one" or "one another", not a count.
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "dozen": 12,
}
WORD_NUMBER = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))

CURRENCY = r"(?:\$|usd|ksh|kes|sh|eur|gbp|£|€)"
# the comma group must repeat at least once, else "2022" is split into "202" + "2"
NUMBER = (r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
          r"|\b(?:" + WORD_NUMBER + r")\b")

FIGURE_RE = re.compile(
    rf"(?P<currency>{CURRENCY})?\s*(?P<value>{NUMBER})\s*"
    rf"(?P<scale>hundred|thousand|million|billion|trillion|bn|tn|mn|[kmb])?(?![a-z])\s*"
    rf"(?P<percent>per cent|percent|%)?",
    re.I,
)

TIME_UNITS = {
    "hour": "hours", "hours": "hours", "day": "days", "days": "days",
    "week": "weeks", "weeks": "weeks", "month": "months", "months": "months",
    "year": "years", "years": "years",
}

# What kind of casualty count a figure is, so that a death toll is never placed
# beside an injury count as if they were one number.
CASUALTY_STATES = {
    "killed": "dead", "kill": "dead", "dead": "dead", "death": "dead",
    "deaths": "dead", "died": "dead", "die": "dead", "toll": "dead",
    "fatalities": "dead", "fatality": "dead", "casualties": "dead",
    "casualty": "dead", "perished": "dead",
    "missing": "missing", "unaccounted": "missing",
    "injured": "injured", "wounded": "injured", "hurt": "injured",
    "displaced": "displaced", "homeless": "displaced",
    "arrested": "arrested", "detained": "arrested",
    "rescued": "rescued", "evacuated": "rescued",
}

PERSON_NOUNS = {
    "people", "person", "persons", "resident", "residents", "leader", "leaders",
    "worker", "workers", "trader", "traders", "student", "students", "voter",
    "voters", "delegate", "delegates", "teacher", "teachers", "farmer", "farmers",
    "officer", "officers", "patient", "patients", "family", "families",
    "household", "households", "refugee", "refugees", "passenger", "passengers",
    "victim", "victims", "survivor", "survivors", "civilian", "civilians",
}

# nouns that mark a bare number as a sum of money
MONEY_NOUNS = {
    "investment", "investments", "funding", "budget", "budgets", "revenue",
    "worth", "cost", "costs", "fdi", "capital", "loan", "loans", "debt",
    "refund", "aid", "grant", "grants", "profit", "turnover", "sales",
    "salary", "salaries", "wage", "wages", "allocation", "bailout",
}

PERCENT_WORDS = {"percent", "per", "cent", "%"}

# currency is shown as a label beside the figure, so a reader can see when two
# sums are quoted in different money, or when one does not say which money it is
CURRENCY_CODES = {
    "$": "usd", "usd": "usd",
    "£": "gbp", "gbp": "gbp",
    "€": "eur", "eur": "eur",
    "ksh": "kes", "kes": "kes", "sh": "kes",
}

# phrases that mark a running total rather than one event: "4 died in Sunday's
# crash" and "3,200 road deaths since January" are both true, and different
CUMULATIVE_MARKERS = (
    "since", "so far", "to date", "this year", "last year", "nationally",
    "in total", "altogether", "annually", "cumulative", "year to date",
    "over the past", "already this", "between january", "each year",
    "across the two", "both countries", "combined", "in total across",
    "on both sides", "overall", "nationwide",
)

# "died at 34" and "aged 34" give a person's age, not a body count
AGE_PATTERN = re.compile(
    r"\b(?:aged|age of|at the age of|died at|dies at|was)\s*$", re.I)

# words that are never the thing being counted, so they cannot become a unit
NON_UNIT_NOUNS = {
    "time", "way", "part", "number", "total", "case", "point", "kind", "sort",
    "lot", "bit", "end", "side", "level", "rate", "value", "result", "figure",
    "one", "other", "same", "such", "own", "half", "third", "quarter",
}

# scale words belong to the number, not to what it counts
SCALE_WORDS = {"hundred", "thousand", "million", "billion", "trillion",
               "bn", "tn", "mn"}

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "from", "with", "by", "as", "is", "are", "was", "were", "be", "been", "has",
    "have", "had", "that", "this", "these", "those", "it", "its", "their", "his",
    "her", "they", "them", "than", "then", "there", "over", "under", "after",
    "before", "into", "about", "more", "most", "least", "some", "new", "now",
    "across", "within", "during", "through", "near", "around", "between",
    "among", "since", "until", "against", "per", "each", "every", "another",
    "also", "will", "would", "can", "could", "may", "still", "yet", "not",
    # reporting verbs carry no subject information
    "said", "says", "say", "told", "confirmed", "announced", "reported",
    "according", "shows", "showed", "show", "data", "report", "reports",
    "gives", "give", "given", "gave", "reached", "reach", "rose", "stood",
    "raised", "remain", "remains", "remained", "added", "noted", "revealed",
}

# entity types that name the place a claim is about
SCOPE_ENT_TYPES = {"GPE", "LOC", "NORP", "FAC"}


def _words(text):
    return re.findall(r"[A-Za-z][A-Za-z'-]*|%", text.lower())


def _singular(word):
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _scan_units(words):
    """Nearest unit word wins, with one exception.

    A generic person noun yields to a casualty state later in the same window:
    "1,500 people are missing" is a missing count, not a head count. Time, money
    and percent hits are specific enough to take as they come, so "90 days to
    identify the dead" stays a duration.
    """
    words = list(words)
    for index, word in enumerate(words):
        if word in TIME_UNITS:
            return TIME_UNITS[word], word, None
        if word in CASUALTY_STATES:
            return "people", None, CASUALTY_STATES[word]
        if word in PERSON_NOUNS:
            state = next((CASUALTY_STATES[w] for w in words[index + 1:] if w in CASUALTY_STATES), None)
            return "people", word, state
        if word in PERCENT_WORDS:
            return "percent", None, None
        if word in MONEY_NOUNS:
            return "currency", None, None
    return None, None, None


def _is_age(sentence, match):
    """True when the number is somebody's age rather than a count of people."""
    return bool(AGE_PATTERN.search(sentence[max(0, match.start() - 24):match.start()]))


def _counted_noun(words, max_span=4):
    """The plain noun a bare count attaches to: "20 hospitals" -> "hospital".

    Noun phrases are head-final, so the run of words after the number is read up
    to the first preposition or verb and the LAST word is taken: "1,000 paid
    internship opportunities" counts opportunities, not "paid".
    """
    span = []
    for word in words:
        if word in STOPWORDS or word in SCALE_WORDS or word in NON_UNIT_NOUNS:
            break
        if len(word) < 3 or not word.isalpha():
            break
        span.append(word)
        if len(span) >= max_span:
            break
    return _singular(span[-1]) if span else None


def figure_unit(match, sentence, window_start, window_end):
    """What this one figure is counting, read from the words next to it.

    The window stops at the neighbouring numbers so an adjacent figure cannot lend
    its unit: in "10,000 leaders given 90 days", the 10,000 never sees "days".
    Returns (unit, unit_word, state) - unit_word is the token to drop from the
    subject, state the casualty state when there is one.
    """
    if match.group("percent"):
        return "percent", None, None
    # a currency symbol settles it; reading the words after it first would take
    # the "year" in "$3.2 billion this year" as a duration
    if match.group("currency"):
        return "currency", None, None

    unit, unit_word, state = _scan_units(_words(sentence[match.end():window_end]))
    if unit:
        return unit, unit_word, state

    # "the death toll rose to 47" - the unit sits before the number
    head_start = max(window_start, match.start() - 60)
    unit, unit_word, state = _scan_units(reversed(_words(sentence[head_start:match.start()])))
    if unit:
        return unit, unit_word, state

    if (match.group("scale") or "").lower() in SCALE_WORDS:
        return "currency", None, None

    # a plain count of ordinary things - hospitals, schools, seats
    noun = _counted_noun(_words(sentence[match.end():window_end]))
    if noun:
        return noun, noun, None

    return None, None, None


def extract_subject(text, unit_word=None):
    """The words describing what a figure is about.

    Units, casualty states and stopwords are dropped because they appear around
    every figure of that kind. Acronyms are recorded so "FDI" can be recognised
    as "foreign direct investment".
    """
    tokens, ordered, upper = set(), [], set()
    for raw in re.findall(r"[A-Za-z][A-Za-z'-]*", text):
        word = raw.lower()
        if word in STOPWORDS or word in TIME_UNITS or word in PERSON_NOUNS:
            continue
        if word in CASUALTY_STATES or word in PERCENT_WORDS or word in SCALE_WORDS:
            continue
        if len(word) < 3:
            continue
        stem = _singular(word)
        tokens.add(stem)
        ordered.append(stem)
        if raw.isupper() and len(raw) >= 3:
            upper.add(word)

    if unit_word:
        tokens.discard(_singular(unit_word))

    acronyms = set()
    for start in range(len(ordered)):
        for span in (3, 4):
            if start + span <= len(ordered):
                acronyms.add("".join(w[0] for w in ordered[start:start + span]))

    return {"tokens": tokens, "acronyms": acronyms, "upper": upper}


def currency_code(match):
    """usd / gbp / kes when the sum carries a symbol, else None for "2.8 billion"."""
    symbol = (match.group("currency") or "").lower()
    return CURRENCY_CODES.get(symbol, symbol or None)


def _sentence_state(sentence):
    """The casualty state of the whole sentence, when it names exactly one.

    Catches "County officials put the number killed in the raid at 23 civilians",
    where "killed" is too far from "23" for the windowed scan. A sentence naming
    two states - "12 died and 30 were injured" - gets none, rather than a guess.
    """
    found = {CASUALTY_STATES[w] for w in _words(sentence) if w in CASUALTY_STATES}
    return found.pop() if len(found) == 1 else None


def parse_figures(sentence):
    """Every figure in a sentence, as a value with its unit, state and subject."""
    matches = [m for m in FIGURE_RE.finditer(sentence) if m.group("value")]

    figures = []
    for index, match in enumerate(matches):
        raw = match.group("value")
        spelled = NUMBER_WORDS.get(raw.strip().lower())
        if spelled is not None:
            value = float(spelled)
        else:
            try:
                value = float(raw.replace(",", ""))
            except ValueError:
                continue

        scale = (match.group("scale") or "").lower()
        if scale:
            value *= SCALES.get(scale, 1)

        # bare years are almost never the quantity being reported
        if not scale and not match.group("currency") and 1900 <= value <= 2100:
            continue

        # "the A8 road" and "Boeing 737" are names, not counts: a digit welded to
        # a letter is an identifier. Checked against the character immediately
        # before the digits, since the match itself starts at the space.
        value_start = match.start("value")
        if (spelled is None and value_start > 0
                and sentence[value_start - 1].isalpha()):
            continue

        window_start = matches[index - 1].end() if index else 0
        window_end = matches[index + 1].start() if index + 1 < len(matches) else len(sentence)
        unit, unit_word, state = figure_unit(match, sentence, window_start, window_end)
        if unit == "people" and not state:
            state = _sentence_state(sentence)
        if state and _is_age(sentence, match):
            # "Ugandan King Oyo dies at 34" is an age, not a death toll
            unit, state = None, None

        figures.append({
            "value": value,
            "text": match.group(0).strip(),
            "unit": unit,
            "state": state,
            "currency": currency_code(match),
            "subject": extract_subject(sentence, unit_word),
        })
    return figures


def cluster_vocabulary(claims, df_limit=SUBJECT_DF_LIMIT, min_claims=5):
    """Words so common across a story's claims that they describe the story itself.

    Every claim in a Kenyan politics story says "Ruto" or "president", so those
    words would otherwise link unrelated figures from the same story. Counted over
    all claims, not only those with a figure, for a steadier sample; below
    min_claims the counts are too small to use.
    """
    if len(claims) < min_claims:
        return set()

    document_frequency = Counter()
    for claim in claims:
        document_frequency.update(extract_subject(claim["text"])["tokens"])

    cutoff = df_limit * len(claims)
    return {term for term, count in document_frequency.items() if count > cutoff}


def is_cumulative(sentence):
    """True when the sentence reports a running total rather than one event."""
    lowered = sentence.lower()
    return any(marker in lowered for marker in CUMULATIVE_MARKERS)


def claim_scope(claim):
    """The places a claim is about, from its named entities.

    Keeps casualty figures about different places apart, so "558 missing on the
    Chinese side" and "826 missing in Nepal" are never shown as one count.
    """
    entities = claim.get("entities") or []
    return frozenset(
        text.lower().strip() for text, label in entities if label in SCOPE_ENT_TYPES
    )
