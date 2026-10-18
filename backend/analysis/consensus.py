"""Coverage: for each fact in a story, which outlets carried it and which did not.

Claims from every readable article are grouped by meaning - two sentences land in
the same group when their embeddings are close enough to be reporting the same
fact. Then it is set arithmetic, with no model making any judgement:

    reported_by   outlets with a claim in the group that says what the fact says
    related       outlets whose claim is close but says something else
    omitted_by    outlets we could read that have no claim in the group

Closeness alone merged different facts. In a hand-checked sample of 30
cross-outlet pairs it had grouped, 17 were different facts: the Health CS saying
the Ebola patient was a Kenyan citizen, filed as the same fact as the CS
describing the patient's route through Uganda. Each pair is now also put to
NLI (backend/nlp/nli.py), read both ways. If neither sentence implies the
other, the outlet is "related": shown with its own sentence, neither credited
with the fact nor counted as leaving it out. NLI wrongly splits about one pair
in five that does share a fact - "Sale 42 on September 29" told with different
details - and the related state is what keeps those from becoming false
omissions. On the sample: wrong merges 17 to 1, false omissions none.

Outlets we could not read at all are in neither list, which is what keeps the
omission column honest. An outlet whose article was paywalled or blocked produced
no claims, so counting it would make it appear to have left out every fact in
the story.

Nothing here decides whether a fact is true, or whether two outlets agree.
"""
import numpy as np

from backend.config import CLAIM_MATCH_MAX_DISTANCE, CLAIM_MATCH_NLI
from backend.nlp.embeddings import model as embed_model
from backend.nlp.nli import relations

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

    groups = group_claims(claims)
    # one judgement per member: does its sentence say what the anchor says?
    pairs = [(claims[seed]["text"], claims[m]["text"]) for seed, members in groups for m in members]
    judged = iter(relations(pairs)) if CLAIM_MATCH_NLI and pairs else None

    coverage = []
    for seed, members in groups:
        anchor = claims[seed]
        reporting, related = {anchor.get("source")}, {}
        for m in members:
            relation = next(judged)[0] if judged else "same"
            source = claims[m].get("source")
            if relation == "different":
                related.setdefault(source, claims[m]["text"])
            else:
                reporting.add(source)
        reporting.discard(None)
        # an outlet that carried the fact in one sentence is not "related" for another
        related = {s: text for s, text in related.items() if s and s not in reporting}
        coverage.append({
            "anchor": anchor,
            "reported_by": sorted(reporting),
            "related": [{"source": s, "text": t} for s, t in sorted(related.items())],
            "omitted_by": sorted(readable - reporting - set(related)),
        })
    return coverage
