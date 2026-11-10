"""Which group of reporting verbs a verb belongs to ("said", "criticised", ...).

Kept apart from portrayal.py, which loads spaCy on import (about seven seconds),
so that the web API can group a person's verbs without loading a parser.
"""
from backend.config import REPORTING_VERBS

FAMILY = {verb: family for family, verbs in REPORTING_VERBS.items() for verb in verbs}


def family_of(phrase):
    """The REPORTING_VERBS group for a verb phrase, if it reports speech."""
    if not phrase:
        return None
    words = phrase.split()
    for candidate in (phrase, " ".join(words[:2]), words[0]):
        if candidate in FAMILY:
            return FAMILY[candidate]
    return None
