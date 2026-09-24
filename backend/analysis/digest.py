"""Figure digest: every number in a story, with its source and context.

The digest does not judge figures. It lays out what each outlet reported so the
reader can see and interpret it. Each figure carries its sentence, the sentence
either side, the outlet, a link to the original, and the labels shown beside
it: who it is credited to, its currency, whether it is a running total, and any
breakdown. Casualty state and place are read too, but only to decide which
figures may sit side by side. A number whose unit cannot be read is dropped,
since there is nothing to show it beside or to say about it.

Figures are tiered by how they can be read:

    shared    at least one other outlet published a figure of the same kind
    single    only one outlet published a figure of this kind

digest_groups() then places shared figures that appear to count the same thing
side by side. Placing them together is a layout decision, not a claim that they
agree or disagree - that is for the reader.
"""
import re

from backend.analysis.figures import (
    claim_scope,
    cluster_vocabulary,
    is_cumulative,
    parse_figures,
)

# entity types whose numbers are never reported quantities: dates, clock times,
# rankings. Without this, "16 September" reads as a count of 16 septembers.
NOISE_ENT_TYPES = {"DATE", "TIME", "ORDINAL"}

# How far apart the smallest and largest figure in a group may be before they are
# too unlikely to be counting the same thing to show together. Casualty counts
# get the wide limit because that is where the gap matters: police, hospitals
# and rights groups count the dead differently, and "police said 3 were killed"
# beside "the commission says 11" is exactly what a reader should see. For money
# and counted objects a wide gap has meant two different quantities - $5m for an
# anti-doping programme beside KES 2bn of sponsorship.
MAX_DISPLAY_SPREAD = 3
CASUALTY_DISPLAY_SPREAD = 100

# Words naming who spoke rather than what was counted. The same minister's name
# and title can appear beside two unrelated figures from one statement.
ATTRIBUTION_WORDS = {
    "cabinet", "secretary", "minister", "ministry", "interior", "principal",
    "administration", "national", "deputy", "president", "governor", "senator",
    "senate", "parliament", "assembly", "commissioner", "spokesperson",
    "official", "officials", "authority", "department", "office", "chief",
    "kenya", "kenyan", "kenyans", "government", "state", "county",
}

# "NAIROBI, Kenya Sep 16 - " and similar wire datelines
DATELINE = re.compile(r"^[A-Z][A-Za-z .'-]{2,24},\s+[A-Z][a-z]+[^.]{0,30}?"
                      r"(?:Sept?|Oct|Nov|Dec|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug)[a-z]*\.?\s*\d{1,2}",
                      re.I)

# Who the sentence credits the number to. Deliberately shallow: it reports what
# the article says, it does not check the body said it.
ATTRIBUTION_VERB = re.compile(
    r"\b(?:according to|said|says|told|reported by|data from|figures from|"
    r"revealed|disclosed|announced|confirmed|estimates?)\b", re.I)

AUTHORITY = re.compile(
    r"\b(police|court|judiciary|ministry|government|treasury|parliament|senate|"
    r"KNBS|IEBC|KNCHR|EACC|KRA|CBK|NTSA|IPOA|county|officials?|hospital|morgue|"
    r"union|commission|authority|regulator|census|survey|poll|audit|report|"
    r"Red Cross|UN|WHO|UNICEF|World Bank|IMF|rights group|watchdog)\b", re.I)

TIER_ORDER = {"shared": 0, "single": 1}


def cited_authority(sentence):
    """Who the sentence says the number came from, or None."""
    if not ATTRIBUTION_VERB.search(sentence):
        return None
    match = AUTHORITY.search(sentence)
    return match.group(0) if match else None


def _contains_number(haystack, number):
    """Whole-number containment, so "20" is not found inside "2026"."""
    return re.search(r"(?<![\d,.])" + re.escape(number) + r"(?![\d,.])", haystack) is not None


def is_noise(figure_text, claim):
    """True for numbers that are dates, times or datelines rather than quantities.

    Both checks are narrow on purpose: only the span a date or dateline actually
    occupies counts, so a real figure sitting next to "NAIROBI, Kenya Sep 16"
    is kept.
    """
    stripped = figure_text.strip()
    for text, label in claim.get("entities") or []:
        if label in NOISE_ENT_TYPES and _contains_number(text, stripped):
            return True

    dateline = DATELINE.search(claim["text"])
    return bool(dateline and _contains_number(dateline.group(0), stripped))


def build_digest(claims, articles=None):
    """Every reported figure in the story, labelled, attributed and tiered.

    articles maps each claim back to the URL it came from, so every figure on
    the page links to the original article.
    """
    origins = {a["id"]: a for a in (articles or [])}
    ubiquitous = cluster_vocabulary(claims)
    rows = []
    for claim in claims:
        scope = claim_scope(claim)
        for figure in parse_figures(claim["text"]):
            if not figure["unit"] or is_noise(figure["text"], claim):
                continue
            origin = origins.get(claim.get("article_id")) or {}
            rows.append({
                "value": figure["value"],
                "figure": figure["text"],
                "unit": figure["unit"],
                "state": figure["state"],
                "currency": figure.get("currency") or "unspecified",
                "source": claim.get("source"),
                "credited_to": cited_authority(claim["text"]),
                "cumulative": is_cumulative(claim["text"]),
                "scope": sorted(scope),
                # people and organisations named in the sentence - a speaker's
                # name is never what a figure counts
                "named": sorted({
                    word.lower()
                    for text, label in (claim.get("entities") or [])
                    if label in ("PERSON", "ORG")
                    for word in text.split()
                    if len(word) > 2
                }),
                "subject": sorted(figure["subject"]["tokens"] - ubiquitous)[:6],
                "acronyms": sorted(figure["subject"]["acronyms"]),
                "upper": sorted(figure["subject"]["upper"]),
                "sentence": claim["text"],
                "context": claim.get("context") or claim["text"],
                "url": origin.get("url"),
            })

    # One figure per outlet, sentence and unit. "At least five people, including
    # two police officers, have been killed" is a toll of five with a breakdown,
    # so the largest figure is kept and the rest are carried as its breakdown.
    by_claim = {}
    for row in rows:
        key = (row["source"], row["sentence"], row["unit"])
        kept = by_claim.get(key)
        if kept is None or row["value"] > kept["value"]:
            if kept is not None:
                row.setdefault("breakdown", []).extend(
                    kept.get("breakdown", []) + [kept["figure"]])
            by_claim[key] = row
        else:
            kept.setdefault("breakdown", []).append(row["figure"])
    rows = list(by_claim.values())

    # the same figure picked up twice from overlapping context windows
    seen, unique = set(), []
    for row in rows:
        key = (row["source"], row["value"], row["unit"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    rows = unique

    for row in rows:
        peers = [
            other for other in rows
            if other is not row
            and other["unit"] == row["unit"]
            and other["source"] != row["source"]
        ]
        row["peers"] = len(peers)
        row["tier"] = "shared" if peers else "single"

    rows.sort(key=lambda r: (TIER_ORDER[r["tier"]], -r["peers"], r["unit"], r["value"]))
    return rows


def rank_by_similarity(members):
    """Order a group so the most closely matching claims come first.

    Each figure's surrounding text is embedded and scored against the group's
    centroid. Two outlets restating one figure sit together at the top; a figure
    whose sentence is about something slightly different falls to the bottom,
    where its own context shows why.
    """
    if len(members) < 2:
        return members

    import numpy as np

    from backend.nlp.embeddings import model as embed_model

    vectors = np.asarray(embed_model.encode(
        [row.get("context") or row["sentence"] for row in members],
        normalize_embeddings=True))
    centroid = vectors.mean(axis=0)
    norm = np.linalg.norm(centroid)
    scores = vectors @ (centroid / norm) if norm else np.ones(len(members))
    ranked = sorted(zip(scores, members, strict=True),
                    key=lambda pair: -round(float(pair[0]), 3))
    return [row for _, row in ranked]


def _distinctive(row):
    """Subject words minus any that name whoever was speaking."""
    named = set(row.get("named") or [])
    return {
        t for t in (row.get("subject") or [])
        if t not in ATTRIBUTION_WORDS and t not in named
    }


def _stem(word):
    """Crude suffix stripping, enough to join a verb to its noun."""
    for suffix in ("ing", "ed", "es", "s", "e"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[:-len(suffix)]
    return word


def _same_subject(a, b):
    """Should these two figures be shown side by side?

    Casualty figures: yes when they are the same kind of count (both dead, both
    injured...), both single-event or both running totals, and not about two
    different named places. Their subject words are not compared, because the
    informative words - "killed", "toll" - are exactly the ones stripped out as
    the state. "The death toll rose to 47" and "officials confirmed 52 dead"
    share nothing else.

    Everything else: yes when their subject words overlap, after removing the
    names of whoever was quoted. An acronym matching its expansion ("FDI",
    "foreign direct investment") or a verb matching its noun ("collapsed",
    "collapse") also counts.
    """
    if a.get("state") != b.get("state"):
        return False

    if a.get("state"):
        if bool(a.get("cumulative")) != bool(b.get("cumulative")):
            return False
        left_scope, right_scope = set(a.get("scope") or []), set(b.get("scope") or [])
        return not (left_scope and right_scope and not (left_scope & right_scope))

    left, right = _distinctive(a), _distinctive(b)
    if not left or not right:
        return True          # nothing distinctive to go on; leave them together
    if left & right:
        return True
    if (set(a.get("upper") or []) & set(b.get("acronyms") or [])
            or set(b.get("upper") or []) & set(a.get("acronyms") or [])):
        return True
    return bool({_stem(t) for t in left} & {_stem(t) for t in right})


def _partition_by_subject(members):
    """Split same-unit figures into sets that are about the same thing.

    Complete linkage: a figure joins a set only if it matches every figure
    already in it, so one loosely related number cannot chain two unrelated
    ones together.
    """
    partitions = []
    for row in members:
        for partition in partitions:
            if all(_same_subject(row, other) for other in partition):
                partition.append(row)
                break
        else:
            partitions.append([row])
    return partitions


def _spread(members):
    return (max(r["value"] for r in members)
            / max(min(r["value"] for r in members), 1e-9))


def _spread_limit(members):
    """Casualty counts get the wide limit; everything else the narrow one."""
    if all(r.get("state") for r in members):
        return CASUALTY_DISPLAY_SPREAD
    return MAX_DISPLAY_SPREAD


def digest_groups(rows):
    """Shared figures that appear to count the same thing, for side-by-side display.

    A group needs figures from at least two outlets, and a range narrow enough
    that the figures plausibly measure one quantity.
    """
    buckets = {}
    for row in rows:
        if row["tier"] == "shared":
            buckets.setdefault(row["unit"], []).append(row)

    groups = []
    for unit, members in buckets.items():
        for partition in _partition_by_subject(members):
            if (len({r["source"] for r in partition}) >= 2
                    and _spread(partition) <= _spread_limit(partition)):
                groups.append({
                    "unit": unit,
                    "sources": sorted({r["source"] for r in partition if r["source"]}),
                    "values": rank_by_similarity(partition),
                })
    return groups


def summarise(rows):
    counts = dict.fromkeys(TIER_ORDER, 0)
    for row in rows:
        counts[row["tier"]] += 1
    return counts
