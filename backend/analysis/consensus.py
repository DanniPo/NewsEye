"""Corroboration and omission: who reports a given fact, and who leaves it out.

Two things are measured here, and only one of them uses a model.

Corroboration is the NLI part: claims close enough in embedding space are compared
against an anchor, and the model says whether each restates it. Across sixteen
clusters this has never once returned "contradicts" - news outlets do not write
sentences that logically negate each other - so the useful output is the weaker
one: these outlets report the same thing.

Omission needs no model at all. Once a fact has been grouped, every source in the
cluster that is absent from that group did not report it. For a media literacy
reader that absence is often the more telling signal: one paper carries the
figure, three do not.
"""
import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from backend.config import NLI_MAX_COSINE_DISTANCE, NLI_MODEL
from backend.nlp.embeddings import model as embed_model

# NLI is the expensive stage and returns "neutral" for anything that is not already
# about the same event, so pairs further apart than this never reach the model
BUCKET_SIMILARITY = 1.0 - NLI_MAX_COSINE_DISTANCE
_nli = None

def get_nli():
    global _nli
    if _nli is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tok = AutoTokenizer.from_pretrained(NLI_MODEL)
        mdl = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL).to(device).eval()
        _nli = (tok, mdl, device)
    return _nli

def bucket_claims(claims):
    """Group claims about the same fact, so NLI only ever sees close pairs.

    Returns (seed, [(index, cosine_distance)]) per bucket. The distance is kept so
    the report can show how near a pair had to be before NLI was asked at all.
    """
    if not claims:
        return []

    vectors = np.asarray(embed_model.encode([c["text"] for c in claims],
                                            normalize_embeddings=True))
    unassigned = set(range(len(claims)))
    buckets = []

    while unassigned:
        seed = min(unassigned)
        unassigned.discard(seed)
        similarities = vectors @ vectors[seed]
        members = [(other, 1.0 - float(similarities[other]))
                   for other in sorted(unassigned)
                   if float(similarities[other]) >= BUCKET_SIMILARITY]
        unassigned -= {index for index, _ in members}
        if members:
            buckets.append((seed, members))
    return buckets

def normalize_relation(label):
    """Map a model's label vocabulary onto supports / contradicts / neutral."""
    text = label.lower()
    if "contradict" in text:
        return "contradicts"
    # guard against substring traps: "not_entailment" also contains "entail"
    if text.startswith("not") or "neutral" in text:
        return "neutral"
    if "entail" in text:
        return "supports"
    return "neutral"

def compare_to_anchor(anchor_text, other_texts, batch_size=8):
    """Relation of each claim to the anchor: supports, contradicts or neutral."""
    if not other_texts:
        return []

    tok, mdl, device = get_nli()
    labels = [mdl.config.id2label[i] for i in range(mdl.config.num_labels)]
    results = []

    for start in range(0, len(other_texts), batch_size):
        chunk = other_texts[start:start + batch_size]
        encoded = tok([anchor_text] * len(chunk), chunk,
                      return_tensors="pt", truncation=True, padding=True, max_length=256).to(device)
        with torch.no_grad():
            probs = mdl(**encoded).logits.softmax(-1).cpu().numpy()
        for row in probs:
            best = int(row.argmax())
            results.append((normalize_relation(labels[best]), float(row[best])))
    return results

def analyze_cluster_claims(claims, all_sources=None, unread_sources=None):
    """Groups of one fact: who corroborates it, who contradicts it, who omits it.

    all_sources must be only the outlets whose text we actually read. An article
    that failed to fetch yields no claims, so counting it would make it appear to
    omit every fact in the cluster - People Daily's site blocked us on seven of
    eight articles and would have been reported as withholding everything. Those
    outlets are listed separately as not checked, never as omitting.
    """
    unread = {s for s in (unread_sources or []) if s}
    cluster_sources = set(all_sources or []) | {
        c.get("source") for c in claims if c.get("source")
    }
    cluster_sources -= unread
    cluster_sources.discard(None)
    groups = []
    for seed, bucket in bucket_claims(claims):
        anchor = claims[seed]
        others = [claims[i] for i, _ in bucket]
        relations = compare_to_anchor(anchor["text"], [c["text"] for c in others])

        members = []
        for claim, (_, distance), (relation, score) in zip(others, bucket, relations, strict=True):
            # an outlet restating itself is not a contradiction between sources.
            # Every contradiction this has ever produced on real text was either a
            # same-source pair or two rows of a table, never two papers disagreeing.
            if relation == "contradicts" and claim.get("source") == anchor.get("source"):
                relation = "neutral"
            members.append({"claim": claim, "relation": relation,
                            "confidence": round(score, 3),
                            "distance": round(distance, 3)})
        # count distinct outlets, not claims: several claims often come from one article
        supporting = {m["claim"].get("source") for m in members if m["relation"] == "supports"}
        contradicting = {m["claim"].get("source") for m in members if m["relation"] == "contradicts"}
        all_group_sources = {anchor.get("source")} | {m["claim"].get("source") for m in members}

        reporting = (all_group_sources - {None})
        groups.append({
            "anchor": anchor,
            "members": members,
            "agree": len(supporting),
            "disagree": len(contradicting),
            "corroborated_by": sorted(supporting - {None}),
            "contradicted_by": sorted(contradicting - {None}),
            "reported_by": sorted(reporting),
            # outlets we read that did not carry this fact
            "omitted_by": sorted(cluster_sources - reporting),
            # outlets whose text we could not retrieve - silence here is ours
            "not_checked": sorted(unread),
            "sources": len(reporting),
            "claims": len(bucket) + 1,
        })
    return groups
