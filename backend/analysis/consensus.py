"""Coverage: for each fact in a story, which outlets carried it and which did not.

Claims from every readable article are grouped by meaning - two sentences land in
the same group when their embeddings are close enough to be reporting the same
fact. Then it is set arithmetic, with no model making any judgement:

    reported_by   outlets with a claim in the group
    omitted_by    outlets we could read that have no claim in the group

Outlets we could not read at all are in neither list, which is what keeps the
omission column honest. An outlet whose article was paywalled or blocked produced
no claims, so counting it would make it appear to have left out every fact in
the story.

Nothing here decides whether a fact is true, or whether two outlets agree.
"""
import numpy as np

from backend.config import CLAIM_MATCH_MAX_DISTANCE
from backend.nlp.embeddings import model as embed_model

MATCH_SIMILARITY = 1.0 - CLAIM_MATCH_MAX_DISTANCE


def group_claims(claims):
    """Group claims that say the same thing.

    Greedy: the earliest unassigned claim seeds a group, and every other
    unassigned claim within MATCH_SIMILARITY of it joins. Returns
    (seed_index, [member_index]) for each group that has at least one member
    besides its seed.
    """
    if not claims:
        return []

    vectors = np.asarray(embed_model.encode([c["text"] for c in claims],
                                            normalize_embeddings=True))
    unassigned = set(range(len(claims)))
    groups = []

    while unassigned:
        seed = min(unassigned)
        unassigned.discard(seed)
        similarities = vectors @ vectors[seed]
        members = [other for other in sorted(unassigned)
                   if float(similarities[other]) >= MATCH_SIMILARITY]
        unassigned -= set(members)
        if members:
            groups.append((seed, members))
    return groups


def analyze_cluster_claims(claims, all_sources=None, unread_sources=None):
    """Who carried each fact and who did not.

    all_sources must be only the outlets whose text we actually read. The
    outlets in unread_sources are never reported as omitting anything.
    """
    unread = {s for s in (unread_sources or []) if s}
    readable = set(all_sources or []) | {c.get("source") for c in claims if c.get("source")}
    readable -= unread
    readable.discard(None)

    coverage = []
    for seed, members in group_claims(claims):
        anchor = claims[seed]
        reporting = ({anchor.get("source")}
                     | {claims[i].get("source") for i in members}) - {None}
        coverage.append({
            "anchor": anchor,
            "reported_by": sorted(reporting),
            "omitted_by": sorted(readable - reporting),
        })
    return coverage
