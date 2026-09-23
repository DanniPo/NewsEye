"""Story-level summary and tone for a cluster.

The summary here is extractive: representative_title() picks the member headline
closest to the cluster centroid. The abstractive path that used to live here is
gone - distilbart, trained on CNN/DailyMail, misspelled Kenyan names in 77 of
149 summaries, and no amount of prompt shaping fixes a tokeniser that has never
seen "Kipchumba".
"""
import torch
from transformers import pipeline
from backend.config import SENTIMENT_MODEL

_sentiment = None
DEVICE = 0 if torch.cuda.is_available() else -1

def get_sentiment():
    global _sentiment
    if _sentiment is None:
        _sentiment = pipeline("sentiment-analysis", model=SENTIMENT_MODEL, device=DEVICE)
    return _sentiment

def representative_title(titles):
    """The cluster's most central real headline, chosen not written.

    An abstractive summariser trained on CNN/DailyMail does not know Kenyan
    names: it produced "Ruti" and "Rutu" for Ruto, "Karuta" for Karua, "Mutari"
    for Muturi. 77 of 149 cluster summaries contained a capitalised word that
    appeared in no source headline. Misspelling the president on a media literacy
    site is not a tradeoff worth making for slightly smoother prose.

    A headline is already a human-written summary of its own story, so the
    honest summary of a cluster is whichever headline sits closest to the
    middle of it. Nothing can be invented because nothing is generated.
    """
    import numpy as np
    from backend.nlp.embeddings import model as embed_model

    cleaned = []
    seen = set()
    for title in titles:
        text = " ".join((title or "").split())
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            cleaned.append(text)

    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]

    vectors = np.asarray(embed_model.encode(cleaned, normalize_embeddings=True))
    centroid = vectors.mean(axis=0)
    # the headline nearest the centre of the cluster is the one that best
    # represents what every outlet agreed the story was
    return cleaned[int((vectors @ centroid).argmax())]


def summarize_titles(titles, max_titles=12, num_beams=1):
    """Passive-tier summary for a cluster: an actual headline from it.

    Kept under the original name so callers do not change.
    """
    return representative_title(list(titles)[:max_titles])


def score_tone(texts, batch_size=16):
    """Average sentiment across articles, reported as a single label and score.

    The model is three-class (negative / neutral / positive) and trained on
    social and news-adjacent text, replacing a binary SST-2 movie-review model
    that had no way to say "neutral" and returned 0.99 on routine political
    reporting. The signed score is P(positive) - P(negative), so an article the
    model reads as mostly neutral lands near zero instead of being forced to a
    pole.

    This is document-level tone, which for news is weak evidence on its own -
    a flood is reported negatively by everyone. See analysis.framing for the
    comparison that carries the signal: the same entity, scored per source.
    """
    samples = [t[:512] for t in texts if t]
    if not samples:
        return None, 0.0

    results = get_sentiment()(samples, batch_size=batch_size, truncation=True, top_k=None)
    signed = []
    for scores in results:
        by_label = {row["label"].lower(): row["score"] for row in scores}
        signed.append(by_label.get("positive", 0.0) - by_label.get("negative", 0.0))

    mean = sum(signed) / len(signed)
    label = "positive" if mean > 0.15 else "negative" if mean < -0.15 else "mixed"
    return label, round(mean, 3)
