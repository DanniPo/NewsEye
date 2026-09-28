import torch
from transformers import pipeline

from backend.config import (
    FALLBACK_LABEL,
    TOPIC_CONFIDENCE_THRESHOLD,
    TOPIC_LABELS,
    ZERO_SHOT_MODEL,
)

DEVICE = 0 if torch.cuda.is_available() else -1
classifier = pipeline("zero-shot-classification", model=ZERO_SHOT_MODEL, device=DEVICE)

def _pick(result: dict) -> tuple:
    label, score = result["labels"][0], result["scores"][0]
    if score < TOPIC_CONFIDENCE_THRESHOLD:
        label = FALLBACK_LABEL
    return label, round(score, 3)

def classify_topic(headline: str) -> tuple:
    return _pick(classifier(headline, candidate_labels=TOPIC_LABELS))

def classify_topics_batch(headlines: list, batch_size: int = 16) -> list:
    # passing a list lets the pipeline batch inputs into single GPU forward passes
    results = classifier(headlines, candidate_labels=TOPIC_LABELS, batch_size=batch_size)
    return [_pick(r) for r in results]