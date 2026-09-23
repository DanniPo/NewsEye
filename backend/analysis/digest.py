"""Figure digest: show every number with its context, and rank it. Judge nothing.

Deciding which figures contradict has failed consistently: zero true positives in
151 clusters, and every candidate that fired was a parts-versus-whole, an age, a
currency conversion or two different quantities. A human reading two sentences
side by side gets it right immediately. The machine does not.

So this inverts the job. All the machinery built for the verdict - units,
casualty states, subjects, currency, scope, cumulative markers - is reused as
*display metadata and ranking*, never as a decision. The reader sees what each
outlet reported and decides for themselves, which is what a media literacy tool
should be doing anyway.

Three tiers, most comparable first:
  comparable  another outlet published a figure in the same unit and scope
  context     a recognisable quantity, but only one outlet reported it
  unclassed   a number we could not type - dates, page furniture, fragments
"""
import re

from backend.analysis.figures import (
    claim_scope, classify_measure, cluster_vocabulary, is_cumulative, parse_figures,
)

# spans whose numbers are never quantities being reported: a date, a clock time,
# a ranking. They are not judgement calls, so dropping them costs the reader
# nothing and keeps the untyped tier small enough to skim.
NOISE_ENT_TYPES = {"DATE", "TIME", "ORDINAL"}

# Figures of one kind that span more than this are not measuring one thing, and
# presenting them as a comparison implies a relationship that is not there - a
# group ran from 66 to Sh391.7 billion and was captioned "spread 15151515152x".
# The reader is the judge of which number is right; the machine still owes them
# an honest claim about what sits side by side.
#
# Measured over 21 cross-source groups from 20 live clusters, spread predicted
# junk well: $5m for an anti-doping programme beside KES 2bn of sponsorship
# (400x), 14 bodies identified beside 443 held (32x), 12 milk coolers for one
# county beside 230 nationwide (19x), the 81st UN session read as a quantity
# (10x). A flat 3x cap took that surface from 67% to 100% precision on the live
# sample - and then the test suite caught what the sample had not contained:
# "police said 3 protesters were killed" against "the rights commission says 11"
# is a 3.67x spread and is the single most important comparison this project
# exists to show. Optimising the cap on live data alone would have deleted the
# product's best case.
#
# So the cap depends on what is being counted. A casualty count whose state and
# place already match is exactly where a wide gap is the finding: police,
# hospitals and rights groups count the dead differently and the size of the
# disagreement is the point. Anything else - sums of money, counted objects -
# gets the tight cap, because there a wide gap has always meant two different
# quantities rather than two accounts of one.
MAX_DISPLAY_SPREAD = 3
CASUALTY_DISPLAY_SPREAD = 100

# Words naming who spoke, not what was counted. "Interior Cabinet Secretary
# Kipchumba Murkomen has told the Senate" appears verbatim beside both the 1,189
# sentenced and the 121,000 incarcerated, so those two figures shared four
# subject tokens - all of them the minister's name and title - while the two
# genuine matches shared only "goonism". Attribution must not count as subject.
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

# who the sentence credits the number to. Detection is deliberately shallow: it
# reports what the article says, it does not verify the body exists or agreed.
ATTRIBUTION_VERB = re.compile(
    r"\b(?:according to|said|says|told|reported by|data from|figures from|"
    r"revealed|disclosed|announced|confirmed|estimates?)\b", re.I)

AUTHORITY = re.compile(
    r"\b(police|court|judiciary|ministry|government|treasury|parliament|senate|"
    r"KNBS|IEBC|KNCHR|EACC|KRA|CBK|NTSA|IPOA|county|officials?|hospital|morgue|"
    r"union|commission|authority|regulator|census|survey|poll|audit|report|"
    r"Red Cross|UN|WHO|UNICEF|World Bank|IMF|rights group|watchdog)\b", re.I)


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

    The reader is the filter for anything genuinely ambiguous, but a publication
    date is not ambiguous - it is simply not a reported quantity. Dropping those
    keeps the untyped tier small enough to skim.

    Both checks are deliberately narrow. Matching a figure anywhere in the first
    60 characters of a datelined sentence threw away Capital FM's "1,189
    sentenced" because it happened to sit near "NAIROBI, Kenya Sep 16"; only the
    span the dateline actually occupies counts. Plain substring matching would
    have dropped "20" for appearing inside "2026".
    """
    stripped = figure_text.strip()
    for text, label in claim.get("entities") or []:
        if label in NOISE_ENT_TYPES and _contains_number(text, stripped):
            return True

    dateline = DATELINE.search(claim["text"])
    return bool(dateline and _contains_number(dateline.group(0), stripped))


def build_digest(claims, articles=None):
    """Every reported figure in the cluster, typed, attributed and tiered.

    articles maps each claim back to the headline and URL it came from. Without
    somewhere to go and read the original, a number on a comparison screen is
    just another number.
    """
    origins = {a["id"]: a for a in (articles or [])}
    ubiquitous = cluster_vocabulary(claims)
    rows, dropped = [], 0
    for claim in claims:
        measure = classify_measure(claim["text"])
        scope = claim_scope(claim)
        for figure in parse_figures(claim["text"]):
            if is_noise(figure["text"], claim):
                dropped += 1
                continue
            rows.append({
                "value": figure["value"],
                "figure": figure["text"],
                "unit": figure["unit"],
                "state": figure["state"],
                # shown as context, never as a gate: "11bn", "$12bn" and
                # "KSh 12bn" all belong side by side so the reader can see that
                # one of them does not say which money it means
                "currency": figure.get("currency") or "unspecified",
                "measure": measure,
                "source": claim.get("source"),
                "credited_to": cited_authority(claim["text"]),
                "cumulative": is_cumulative(claim["text"]),
                "scope": sorted(scope),
                # whoever is named in the sentence. A speaker's name is never
                # what a figure counts, and "Kipchumba" was the last token
                # holding 1,189-sentenced and 121,000-incarcerated together.
                "named": sorted({
                    word.lower()
                    for text, label in (claim.get("entities") or [])
                    if label in ("PERSON", "ORG")
                    for word in text.split()
                    if len(word) > 2
                }),
                "subject": sorted(figure["subject"]["tokens"] - ubiquitous)[:6],
                # kept so "FDI" can still be matched against "foreign direct
                # investment": the initials of each run of subject words, and
                # the all-caps tokens that might be one of them
                "acronyms": sorted(figure["subject"]["acronyms"]),
                "upper": sorted(figure["subject"]["upper"]),
                "sentence": claim["text"],
                # the sentence either side, so the reader can see what the
                # number is attached to without leaving the page
                "context": claim.get("context") or claim["text"],
                "article_id": claim.get("article_id"),
                # publication time, so a group can be read as a timeline: a toll
                # that only rises is a story being updated, not a disagreement
                "published": (claim.get("published_utc").isoformat()
                              if hasattr(claim.get("published_utc"), "isoformat")
                              else claim.get("published_utc")),
                "article_title": (origins.get(claim.get("article_id")) or {}).get("title"),
                "url": (origins.get(claim.get("article_id")) or {}).get("url"),
            })

    # One sentence, one claim. "At least five people, including two police
    # officers, have been killed" is a toll of five with a breakdown, not an
    # outlet disagreeing with itself - but it parsed as two rows in the same
    # unit, so KBC appeared twice in the Isiolo panel at 5 and at 2.
    # Keep the largest figure per (outlet, sentence, unit) and carry the rest
    # as a breakdown the reader can see.
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

    # and the same figure restated across overlapping extraction windows is
    # still one report
    seen, unique = set(), []
    for row in rows:
        key = (row["source"], row["value"], row["unit"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    rows = unique

    # Comparable means only: another outlet published the same kind of quantity.
    # The conflict detector also required matching places and matching scope, and
    # that is correct when the machine is issuing a verdict - it is what stops it
    # calling 558-on-the-Chinese-side a rival of 826-in-Nepal. Here the reader is
    # the judge, and those same gates hid the most interesting comparison in the
    # corpus: 1,189 sentenced against 121,000 incarcerated, same minister, same
    # session. Scope and cumulative stay on the row as labels so the reader can
    # see why two numbers may not be measuring the same thing.
    for row in rows:
        peers = [
            other for other in rows
            if other is not row
            and other["unit"] and other["unit"] == row["unit"]
            and other["source"] != row["source"]
        ]
        row["peers"] = len(peers)
        row["tier"] = ("comparable" if row["unit"] and peers
                       else "context" if row["unit"]
                       else "unclassed")

    order = {"comparable": 0, "context": 1, "unclassed": 2}
    rows.sort(key=lambda r: (order[r["tier"]], -r["peers"], r["unit"] or "zz", r["value"]))
    for row in rows:
        row["noise_dropped"] = dropped
    return rows


def rank_by_similarity(members):
    """Order a group so near-identical claims sit together and outliers fall last.

    Value order tells the reader the numeric spread but nothing about whether the
    numbers are even about the same thing. Sentence similarity does: two outlets
    restating one Senate figure score high against each other, while a third
    reporting a different quantity from the same session scores low and drops to
    the bottom of the group, where its own context explains why.

    The score is cosine similarity to the group's centroid, so it is a property
    of the group rather than of whichever row happened to be first.
    """
    if len(members) < 2:
        for row in members:
            row["similarity"] = 1.0
        return members

    import numpy as np
    from backend.nlp.embeddings import model as embed_model

    vectors = np.asarray(embed_model.encode(
        [row.get("context") or row["sentence"] for row in members],
        normalize_embeddings=True))
    centroid = vectors.mean(axis=0)
    norm = np.linalg.norm(centroid)
    scores = vectors @ (centroid / norm) if norm else np.ones(len(members))
    for row, score in zip(members, scores):
        row["similarity"] = round(float(score), 3)
    return sorted(members, key=lambda r: -r["similarity"])


def _distinctive(row):
    """Subject tokens minus every word that names whoever was speaking."""
    named = set(row.get("named") or [])
    return {
        t for t in (row.get("subject") or [])
        if t not in ATTRIBUTION_WORDS and t not in named
    }


def _same_subject(a, b):
    """Do two figures count the same population?

    Unit and tags are not enough. 1,189 sentenced for political violence and
    121,000 young people incarcerated are both people, both credited to the
    Senate, both running totals - and they count different populations. What
    separates them is subject vocabulary with the attribution stripped out.

    Casualty state comes first and is absolute. A death toll and an injury count
    from one incident share every other signal - same place, same event, same
    unit, overlapping vocabulary - so subject matching alone put "12 died" next
    to "30 injured" and presented them as rival counts of one number. They are
    both true and they are not comparable. This guard used to sit in the conflict
    adjudicator; it belongs here, because presenting is now the whole feature.
    """
    left_state, right_state = a.get("state"), b.get("state")
    if left_state != right_state:
        return False

    if left_state:
        # Casualty counts are the one case where the state and the unit are
        # enough on their own. "The death toll rose to 47" and "officials
        # confirmed 52 dead" share no subject vocabulary at all - the words that
        # would match are exactly the ones stripped out as casualty states - so
        # demanding token overlap kept apart the comparison this feature exists
        # to show.
        #
        # Permissiveness here needs its own guards, because subject tokens were
        # the only thing separating one incident from another:
        #   - a running total is not a rival estimate of one event's count
        #     ("4 died in Sunday's crash" vs "3,200 road deaths since January")
        #   - two named places that do not overlap are two different events
        #     ("558 missing on the Chinese side" vs "826 missing in Nepal")
        if bool(a.get("cumulative")) != bool(b.get("cumulative")):
            return False
        left_scope, right_scope = set(a.get("scope") or []), set(b.get("scope") or [])
        if left_scope and right_scope and not (left_scope & right_scope):
            return False
        # Deliberately no subject-token test beyond this point. Requiring one
        # blocked "the death toll rose to 47" against "officials confirmed 52
        # dead", whose only distinctive tokens are "tuesday" and "incident" -
        # the informative words having been stripped out as casualty states.
        # The place gate above is what separates two different incidents, and it
        # works on the entities spaCy attaches to every production claim.
        return True

    left, right = _distinctive(a), _distinctive(b)
    if not left or not right:
        return True          # nothing distinctive to go on; leave them together
    if left & right:
        return True
    # "FDI" against "foreign direct investment"
    if (set(a.get("upper") or []) & set(b.get("acronyms") or [])
            or set(b.get("upper") or []) & set(a.get("acronyms") or [])):
        return True
    # "when the building collapsed" and "injured in the collapse" are the same
    # event described as a verb and as a noun, and the exact-token sets miss each
    # other entirely. Stemming is the fallback, not the primary test, so an
    # over-eager stem cannot pull apart what exact matching already joined.
    return bool({_stem(t) for t in left} & {_stem(t) for t in right})


def _stem(word):
    """Crude suffix stripping, enough to join a verb to its noun."""
    for suffix in ("ing", "ed", "es", "s", "e"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[:-len(suffix)]
    return word


def _partition_by_subject(members):
    """Split a unit group into sets that are actually about the same thing.

    Complete linkage: a figure joins a partition only if it shares subject
    vocabulary with every member, so one loosely-related number cannot chain
    two distinct populations together.
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


def digest_groups(rows, order="similarity"):
    """Comparable rows bundled by what they measure, for side-by-side display."""
    buckets = {}
    for row in rows:
        if row["tier"] != "comparable":
            continue
        buckets.setdefault(row["unit"], []).append(row)

    groups = {}
    for unit, members in buckets.items():
        for index, partition in enumerate(_partition_by_subject(members)):
            groups[(unit, index)] = partition
    orderings = {
        # most representative first, the odd one out last
        "similarity": rank_by_similarity,
        # smallest to largest, for reading the numeric spread
        "value": lambda m: sorted(m, key=lambda r: r["value"]),
        # oldest first, so a figure that grew over time reads as a timeline
        "date": lambda m: sorted(m, key=lambda r: (r.get("published") or "", r["value"])),
    }
    arrange = orderings.get(order, rank_by_similarity)
    return [
        {
            "unit": unit,
            "sources": sorted({r["source"] for r in members if r["source"]}),
            "spread": _spread(members),
            "values": arrange(members),
        }
        for (unit, _), members in groups.items()
        if len({r["source"] for r in members}) >= 2
        and _spread(members) <= _spread_limit(members)
    ]


def _spread(members):
    return (max(r["value"] for r in members)
            / max(min(r["value"] for r in members), 1e-9))


def _spread_limit(members):
    """How far apart two figures may be and still be shown side by side.

    Casualty counts get the generous limit: the whole point of putting a police
    figure next to a rights group's is that they differ, sometimes by a lot.
    Everything else gets the tight one.
    """
    if all(r.get("state") for r in members):
        return CASUALTY_DISPLAY_SPREAD
    return MAX_DISPLAY_SPREAD


def summarise(rows):
    counts = {"comparable": 0, "context": 0, "unclassed": 0}
    for row in rows:
        counts[row["tier"]] += 1
    return counts
