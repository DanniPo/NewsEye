"""Entity framing: how each outlet describes the people and institutions in a story.

Sentiment is scored only on the sentences that name an entity, and averaged per
(entity, outlet) pair - never per article. A whole article's tone says little
(a flood reads negative whoever files it); how one outlet writes about a named
person compared with another outlet is what a reader can learn from.

Each result carries the outlet's average and its sharpest single sentence, so
the reader sees the wording behind the score. Only entities named by at least
two outlets are included.
"""
import re
from collections import defaultdict

from backend.config import (
    CORPUS_UNIVERSAL_TERMS,
    FRAMING_MIN_MENTIONS,
    FRAMING_MIN_SOURCES,
    SENTIMENT_MODEL,
)

# entities that can be described warmly or coldly: people, organisations,
# places, laws, events. A number or a date has no framing.
FRAMED_ENT_TYPES = {"PERSON", "ORG", "GPE", "NORP", "LAW", "EVENT", "FAC", "PRODUCT"}

_TITLE_PREFIX = re.compile(r"^(?:president|mr|mrs|ms|dr|prof|hon|sen|gov)\.?\s+", re.I)
# NER returns "the World Athletics" with the article attached
_LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.I)
_POSSESSIVE = re.compile(r"[\u2019']s\b")
_NOISE = re.compile(r"[^\w\s-]")

# NER sometimes returns a headline fragment as a name ("Martin Kimani Lands Top
# Job"). A real entity is short and has no verb in it.
ENTITY_MAX_TOKENS = 4
_verb_cache = {}
_sentiment = None


def get_sentiment():
    """The three-class sentiment pipeline, loaded once on first use."""
    global _sentiment
    if _sentiment is None:
        import torch
        from transformers import pipeline
        device = 0 if torch.cuda.is_available() else -1
        _sentiment = pipeline("sentiment-analysis", model=SENTIMENT_MODEL, device=device)
    return _sentiment


def looks_like_entity(text):
    """Reject headline fragments masquerading as entity names."""
    words = (text or "").split()
    if not words or len(words) > ENTITY_MAX_TOKENS:
        return False
    key = text.lower()
    if key not in _verb_cache:
        from backend.analysis.claims import get_nlp
        doc = get_nlp()(text)
        _verb_cache[key] = not any(t.pos_ in ("VERB", "AUX") for t in doc)
    return _verb_cache[key]


def normalize_entity(text):
    """Surface form to a comparable key: 'President William Ruto's' -> 'william ruto'."""
    text = _POSSESSIVE.sub("", text or "")
    text = _NOISE.sub(" ", text)
    text = _TITLE_PREFIX.sub("", " ".join(text.split()))
    text = _LEADING_ARTICLE.sub("", text)
    return text.strip().lower()


def _merge_aliases(counts):
    """Fold 'Ruto' and 'William Ruto' together, keeping the commonest wording.

    Two keys merge when one's words are a subset of the other's - the usual
    newspaper pattern of naming someone fully once and by surname thereafter.
    """
    keys = sorted(counts, key=lambda k: (-len(k.split()), -counts[k]))
    canonical = {}
    for key in keys:
        words = set(key.split())
        for existing in canonical.values():
            if words and words <= set(existing.split()):
                canonical[key] = existing
                break
        else:
            canonical[key] = key
    return canonical


def collect_mentions(claims):
    """{entity: [(source, sentence)]} for every entity worth framing."""
    counts = defaultdict(int)
    raw = []
    for claim in claims:
        source = claim.get("source")
        seen = set()
        for text, label in claim.get("entities") or []:
            if label not in FRAMED_ENT_TYPES or not looks_like_entity(text):
                continue
            key = normalize_entity(text)
            if len(key) < 3 or key in seen:
                continue
            # comparing how Kenyan outlets frame "Kenya" measures nothing: the
            # term is in most articles of most clusters. It produced 5 of 11
            # divergences and not one of them told a reader anything.
            if key in CORPUS_UNIVERSAL_TERMS:
                continue
            seen.add(key)
            counts[key] += 1
            raw.append((key, text, source, claim["text"]))

    if not raw:
        return {}

    alias = _merge_aliases(counts)
    display, mentions = {}, defaultdict(list)
    for key, text, source, sentence in raw:
        target = alias.get(key, key)
        # Show the entity the way the papers wrote it, minus NER's stray
        # punctuation. strip() takes a set of characters here, not a substring,
        # which is exactly what is wanted: trim any of these from either end.
        surface = _LEADING_ARTICLE.sub(  # noqa: B005 - character set is deliberate
            "", text.strip(" ()[]{}.,;:’'\""))
        # Capital FM datelines every story "NAIROBI, Kenya Sep 22", so NER hands
        # back the city shouted. Prefer any mixed-case wording of the same name,
        # and only title-case as a last resort - a genuine acronym like KEBS
        # must survive.
        previous = display.get(target)
        if previous is None or (previous.isupper() and not surface.isupper()):
            display[target] = surface if not surface.isupper() or len(surface) <= 5 \
                else surface.title()
        mentions[target].append((source, sentence))
    return {display[k]: v for k, v in mentions.items()}


def sentence_sentiment(sentences, batch_size=16):
    """Signed sentiment per sentence: P(positive) - P(negative), in -1..1."""
    if not sentences:
        return []
    results = get_sentiment()([s[:512] for s in sentences],
                              batch_size=batch_size, truncation=True, top_k=None)
    scores = []
    for row in results:
        by_label = {r["label"].lower(): r["score"] for r in row}
        scores.append(by_label.get("positive", 0.0) - by_label.get("negative", 0.0))
    return scores


def _frame_label(score):
    if score > 0.15:
        return "positive"
    return "negative" if score < -0.15 else "neutral"


def analyze_framing(claims, min_sources=FRAMING_MIN_SOURCES,
                    min_mentions=FRAMING_MIN_MENTIONS):
    """Per entity, how each source describes it, widest gap between outlets first."""
    mentions = collect_mentions(claims)
    comparable = {
        entity: rows for entity, rows in mentions.items()
        if len({source for source, _ in rows if source}) >= min_sources
    }
    if not comparable:
        return []

    # one batched pass over every sentence that needs scoring
    flat = [(entity, source, sentence)
            for entity, rows in comparable.items()
            for source, sentence in rows]
    scores = sentence_sentiment([sentence for _, _, sentence in flat])

    grouped = defaultdict(list)
    for (entity, source, sentence), score in zip(flat, scores, strict=True):
        grouped[(entity, source)].append((score, sentence))

    records = []
    for entity in comparable:
        per_source = []
        for (ent, source), rows in grouped.items():
            if ent != entity or not source or len(rows) < min_mentions:
                continue
            mean = sum(score for score, _ in rows) / len(rows)
            # the sentence that most drives this outlet's score, for the report
            sharpest = max(rows, key=lambda r: abs(r[0]))
            per_source.append({
                "source": source,
                # the outlet's average across every mention of this entity
                "score": round(mean, 3),
                "frame": _frame_label(mean),
                "mentions": len(rows),
                "example": sharpest[1],
                # the quoted sentence's own label. Showing the average beside a
                # single quote implied the label described that quote, so one
                # sentence appeared "neutral" under one entity and "positive"
                # under another - it was the averages differing, not the sentence.
                "example_frame": _frame_label(sharpest[0]),
            })

        if len(per_source) < min_sources:
            continue
        per_source.sort(key=lambda s: s["score"])
        spread = per_source[-1]["score"] - per_source[0]["score"]
        records.append({
            "entity": entity,
            "sources": per_source,
            "spread": round(spread, 3),
        })

    records.sort(key=lambda r: (-r["spread"], r["entity"]))
    return records
