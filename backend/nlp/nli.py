"""Does one sentence say what another says? Natural language inference, read both ways.

Used only to compare two versions of the same thing - two outlets' sentences in
one coverage group, two outlets' quotes of one speaker. Never to decide whether
something is true, whether outlets contradict each other, or how an outlet feels
about anyone: the project measured all three and removed them.

The model is the topic classifier's checkpoint, which is a two-label NLI model,
"entailment" and "not_entailment". It has no contradiction label, so it cannot
report one - which suits a site that never claims a contradiction.

NLI was tried here before and dropped after it "marked a sentence as
contradicting an identical copy of itself at 0.853". That is exactly what an
entailment score of 0.853 looks like when a three-label model's order
(contradiction first) is assumed for this one (entailment first). The index is
read from the model's own config here, never assumed. Read correctly, the same
checkpoint scores an identical pair 0.99 entailment both ways.

Read in both directions, a pair gives one of four relations:

    same          each implies the other           paraphrases, identical quotes
    first_more    the first implies the second     the first adds detail
    second_more   the second implies the first     the second adds detail
    different     neither implies the other        another fact, or a negation
"""
from functools import lru_cache

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from backend.config import NLI_ENTAILS, NLI_MODEL

BATCH_SIZE = 32
# DeBERTa reads 512 tokens; a claim with its context is well inside that
MAX_TOKENS = 512


@lru_cache(maxsize=1)
def _load():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    # float16 only on a GPU: on this laptop's CPU the checkpoint's float16 ran
    # 12x slower than float32 (see backend/nlp/classification.py)
    dtype = torch.float16 if device == "cuda" else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(NLI_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL, dtype=dtype)
    model = model.to(device).eval()
    entail = model.config.label2id.get("entailment")
    if entail is None:
        raise ValueError(f"{NLI_MODEL} has no 'entailment' label: {model.config.id2label}")
    return tokenizer, model, device, entail


def entailment(pairs):
    """P(premise implies hypothesis) for each (premise, hypothesis) pair."""
    if not pairs:
        return []
    tokenizer, model, device, entail = _load()
    scores = []
    for start in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[start:start + BATCH_SIZE]
        inputs = tokenizer([p for p, _ in batch], [h for _, h in batch], return_tensors="pt",
                           padding=True, truncation=True, max_length=MAX_TOKENS).to(device)
        with torch.inference_mode():
            probs = torch.softmax(model(**inputs).logits.float(), dim=-1)[:, entail]
        scores.extend(probs.tolist())
    return scores


def relations(pairs, threshold=NLI_ENTAILS):
    """For each (a, b): (relation, P(a implies b), P(b implies a))."""
    forward = entailment(pairs)
    backward = entailment([(b, a) for a, b in pairs])
    out = []
    for ab, ba in zip(forward, backward, strict=True):
        if ab >= threshold and ba >= threshold:
            relation = "same"
        elif ab >= threshold:
            relation = "first_more"
        elif ba >= threshold:
            relation = "second_more"
        else:
            relation = "different"
        out.append((relation, ab, ba))
    return out


def relation(a, b):
    return relations([(a, b)])[0][0]
