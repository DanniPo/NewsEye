"""Claim extraction: pull factual, checkable sentences out of article text."""
import re

import spacy

from backend.config import (
    CLAIM_CONTEXT_CHARS,
    CLAIM_ENTITY_TYPES,
    CLAIM_MAX_PER_ARTICLE,
    CLAIM_MIN_CHARS,
)

_nlp = None
NUMERIC_HINT = re.compile(r"\d|%|\b(million|billion|percent|per cent)\b", re.I)
# trafilatura keeps tables as pipe-delimited rows. They parse as sentences dense
# with numbers, then get compared against each other as though they were
# assertions - two rows of a fund performance table were reported as an outlet
# contradicting itself.
TABLE_ROW = re.compile(r"\|.*\|")

# Navigation, comment widgets and related-article rails. On pages with little real
# body text - Nation Africa's video pages, for instance - trafilatura falls back
# to this furniture, and it then reads as claims: one outlet was recorded as
# "omitting" another paper's sidebar headline about an inheritance ruling.
FURNITURE = re.compile(
    r"login to join|enable javascript|powered by disqus|also read"
    r"|read more|subscribe|follow us on|advertisement|most popular"
    r"|related stories|sign in|my account|change password"
    r"|watch .{0,40}below|click here|share this|caption for|photo: |image: |file photo", re.I)

def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm", disable=["lemmatizer", "textcat"])
    return _nlp

def extract_claims(text, max_claims=CLAIM_MAX_PER_ARTICLE):
    """Return sentences carrying a checkable fact, with their entities."""
    if not text:
        return []

    doc = get_nlp()(text[:20000])
    sentences = list(doc.sents)
    claims = []
    for position, sent in enumerate(sentences):
        sentence = sent.text.strip().replace("\n", " ")
        if len(sentence) < CLAIM_MIN_CHARS or TABLE_ROW.search(sentence):
            continue
        if FURNITURE.search(sentence):
            continue

        entities = [(e.text, e.label_) for e in sent.ents]
        has_target = any(label in CLAIM_ENTITY_TYPES for _, label in entities)
        if not (has_target or NUMERIC_HINT.search(sentence)):
            continue

        # a figure alone is not evidence; the reader needs enough around it to
        # judge whether two numbers are measuring the same thing. One sentence
        # either side is usually the difference between "1,189 sentenced" and
        # "1,189 sentenced, of whom 300 were minors".
        window = sentences[max(0, position - 1):position + 2]
        context = " ".join(s.text.strip().replace("\n", " ") for s in window)
        claims.append({
            "text": sentence,
            "entities": entities,
            "context": " ".join(context.split())[:CLAIM_CONTEXT_CHARS],
        })
        if len(claims) >= max_claims:
            break
    return claims
