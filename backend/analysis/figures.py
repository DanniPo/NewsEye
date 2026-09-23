"""Parse the numbers out of a sentence, and say what each one counts.

Sentence-level NLI treats "FDI rose to $3.2bn" and "FDI rose to $2.8bn" as
neutral, because neither logically negates the other. Reading the values out
is what makes them comparable at all.

This module only parses and types figures. It used to go on and adjudicate them,
declaring which outlets disagreed, and that was removed: across corpora of 800
and 2,162 articles it produced no true positive. Every firing was a scope
mismatch - a ward prize weighed against a county prize, "six treated at the
scene" against the "eight injured" that included them. Deciding is now the
reader's job, and analysis.digest presents the figures so they can do it.

What survives here is the typing that makes a presentation honest: a figure
carries its unit, its currency, its casualty state, whether it is a running
total, and the geographic scope of the claim it came from. Two numbers are only
ever shown as comparable when they share a unit *and* an overlapping subject.
Bucketing on a sentence-wide measure alone produced pairs like "10,000 leaders"
against "90 trader days": the sentence mentioned days, so every figure in it was
filed as a duration.
"""
import re
from collections import Counter

# a subject term carried by more of the cluster's claims than this identifies the
# cluster, not the figure, so it cannot be used to match two figures
SUBJECT_DF_LIMIT = 0.25

SCALES = {
    "hundred": 1e2, "thousand": 1e3, "k": 1e3,
    "million": 1e6, "m": 1e6, "mn": 1e6,
    "billion": 1e9, "bn": 1e9, "b": 1e9,
    "trillion": 1e12, "tn": 1e12,
}

# News style spells out numbers under ten, so "five people were killed" carried
# no figure at all while "12 people were killed" did. Every casualty count in a
# small incident - the contested ones - was invisible to this module, and the
# synthetic tests missed it because they were all written in digits.
NUMBER_WORDS = {
    # "one" is deliberately absent: in news prose it is almost always "one of
    # the", "no one" or "one another" rather than a count, and including it put
    # phantom 1s into every casualty group.
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

# ordered most-specific first: "traders given 90 days" is a duration, not a people count
MEASURE_KEYWORDS = (
    ("casualties", ("killed", "dead", "death", "deaths", "died", "fatalities",
                    "missing", "injured", "wounded", "casualt")),
    ("share", ("per cent", "percent", "%")),
    ("duration", ("days", "months", "years", "weeks", "hours")),
    ("money", ("investment", "funding", "budget", "revenue", "worth", "cost",
               "fdi", "capital", "loan", "debt", "refund", "billion", "million")),
    ("people", ("people", "residents", "leaders", "workers", "traders",
                "students", "voters", "delegates")),
)

TIME_UNITS = {
    "hour": "hours", "hours": "hours", "day": "days", "days": "days",
    "week": "weeks", "weeks": "weeks", "month": "months", "months": "months",
    "year": "years", "years": "years",
}

# a casualty count's state is what tells the figures apart: 1,300 missing and
# 47 dead are not rival estimates of one number, so the state stays in the subject
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

# what the money is *for* is the subject, so these stay in the subject set
MONEY_NOUNS = {
    "investment", "investments", "funding", "budget", "budgets", "revenue",
    "worth", "cost", "costs", "fdi", "capital", "loan", "loans", "debt",
    "refund", "aid", "grant", "grants", "profit", "turnover", "sales",
    "salary", "salaries", "wage", "wages", "allocation", "bailout",
}

PERCENT_WORDS = {"percent", "per", "cent", "%"}

# "$2.1bn" and "GBP1.6bn" are the same sum quoted twice, not two outlets
# disagreeing, so the currency itself is part of the unit
CURRENCY_CODES = {
    "$": "usd", "usd": "usd",
    "£": "gbp", "gbp": "gbp",
    "€": "eur", "eur": "eur",
    "ksh": "kes", "kes": "kes", "sh": "kes",
}

# a running total is a different quantity from a single incident's count:
# "4 died in Sunday's crash" and "3,200 road deaths since January" are both true
CUMULATIVE_MARKERS = (
    "since", "so far", "to date", "this year", "last year", "nationally",
    "in total", "altogether", "annually", "cumulative", "year to date",
    "over the past", "already this", "between january", "each year",
    # a combined figure is the sum of the parts, not a rival estimate of one
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

# scale words belong to the number, not to what it counts: leaving "billion" in
# the subject made every currency figure overlap every other one
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


def classify_measure(sentence):
    lowered = sentence.lower()
    for measure, keywords in MEASURE_KEYWORDS:
        if any(k in lowered for k in keywords):
            return measure
    return "other"


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

    Without this, every count of an ordinary thing had no unit and was dropped, so
    "the president built 20 hospitals" and "he built 5 hospitals" were never
    compared - exactly the disagreement the feature exists to catch.

    English noun phrases are head-final, so the run of words after the number is
    collected up to the first preposition or verb and the LAST one is the head:
    "1,000 paid internship opportunities" is a count of opportunities, not of
    "paid". Taking the first word made adjectives into units.
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
    """The unit this one figure is counting, read from the words next to it.

    The window stops at the neighbouring numbers so an adjacent figure cannot lend
    its unit: in "10,000 leaders given 90 days", the 10,000 never sees "days".
    Returns (unit, unit_word, state) - unit_word is the token to drop from the
    subject, state the casualty state when there is one.
    """
    if match.group("percent"):
        return "percent", None, None
    # a currency symbol settles it; scanning the tail first would read the "year"
    # in "$3.2 billion this year" as a duration
    if match.group("currency"):
        return "currency", None, None

    unit, unit_word, state = _scan_units(_words(sentence[match.end():window_end]))
    if unit:
        return unit, unit_word, state

    # "FDI doubled to 3.2 billion", "the death toll rose to 47" - the unit sits
    # before the number, so read backwards from it
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


def extract_subject(text, unit_word=None, state=None):
    """What the figure is about, as comparable tokens.

    Units are dropped - every duration mentions "days", so it separates nothing.
    Acronyms are recorded so "FDI" can still match "foreign direct investment".
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

    return {"tokens": tokens, "acronyms": acronyms, "upper": upper, "state": state}


def subjects_overlap(a, b):
    """True when two figures are plausibly about the same thing."""
    if not a or not b:
        return False

    # 1,300 missing and 1,500 dead are not rival estimates of one number
    if a["state"] and b["state"]:
        return a["state"] == b["state"]

    if not a["tokens"] or not b["tokens"]:
        return False
    if a["tokens"] & b["tokens"]:
        return True
    # "FDI" against "foreign direct investment"
    return bool(a["upper"] & b["acronyms"] or b["upper"] & a["acronyms"])


def currency_code(match):
    """usd / gbp / kes when the sum carries a symbol, else None for "2.8 billion"."""
    symbol = (match.group("currency") or "").lower()
    return CURRENCY_CODES.get(symbol, symbol or None)


def parse_figures(sentence):
    """Pull normalized numeric values, with their unit and subject, out of a sentence."""
    matches = []
    for match in FIGURE_RE.finditer(sentence):
        if match.group("value"):
            matches.append(match)

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

        # bare years are almost never the quantity under discussion
        if not scale and not match.group("currency") and 1900 <= value <= 2100:
            continue

        # "the lower A8 road" and "Boeing 737" are names, not counts. A digit
        # welded directly to a letter is an identifier; the check must look at the
        # character immediately before the digits, not before the whole match,
        # which starts at the preceding space.
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
            # "Ugandan King Oyo dies at 34" was being read as a death toll of 34
            unit, state = None, None

        figures.append({
            "value": value,
            "text": match.group(0).strip(),
            "percent": bool(match.group("percent")),
            "unit": unit,
            "state": state,
            "currency": currency_code(match),
            "subject": extract_subject(sentence, unit_word, state),
        })
    return figures


def _sentence_state(sentence):
    """The casualty state of the sentence as a whole, when it has exactly one.

    The windowed scan only sees a few words either side of the number, so
    "County officials put the number killed in the raid at 23 civilians" came
    back stateless: "killed" sits before "the number", nowhere near "23". An
    untyped count cannot be told apart from a death toll, which is how an injury
    figure ended up beside one.

    Only an unambiguous sentence qualifies. "12 died and 30 were injured" names
    two states, and guessing either would put those two figures in one group -
    the exact error this is here to prevent.
    """
    found = {CASUALTY_STATES[w] for w in _words(sentence) if w in CASUALTY_STATES}
    return found.pop() if len(found) == 1 else None


def cluster_vocabulary(claims, df_limit=SUBJECT_DF_LIMIT, min_claims=5):
    """Terms so common in this cluster that they cannot tell two figures apart.

    Every claim in a Kenyan politics cluster says "Ruto", "Kenya" and "president",
    so those words linked a summit head count to a continental population figure.
    Frequencies are counted over all the cluster's claims, not just the ones that
    carry a figure, because that is the larger and steadier sample. Below
    min_claims the frequencies mean nothing, so nothing is cut.
    """
    if len(claims) < min_claims:
        return set()

    document_frequency = Counter()
    for claim in claims:
        document_frequency.update(extract_subject(claim["text"])["tokens"])

    cutoff = df_limit * len(claims)
    return {term for term, count in document_frequency.items() if count > cutoff}


def is_cumulative(sentence):
    """True when the sentence is reporting a running total, not one event."""
    lowered = sentence.lower()
    return any(marker in lowered for marker in CUMULATIVE_MARKERS)


# a figure counted for one place is not a rival estimate of the figure counted
# for another, nor of the two combined
SCOPE_ENT_TYPES = {"GPE", "LOC", "NORP", "FAC"}


def claim_scope(claim):
    """The places a claim is counting over, as a comparable key.

    In the Nepal-Tibet floods, one sentence counted 558 missing "on the Chinese
    side", another 826 "in Nepal", and a third 3,048 across both. Those are parts
    and a whole, not three outlets disagreeing. Requiring the same scope keeps
    them apart.
    """
    entities = claim.get("entities") or []
    return frozenset(
        text.lower().strip() for text, label in entities if label in SCOPE_ENT_TYPES
    )


