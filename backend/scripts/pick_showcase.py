"""Choose stories for a demonstration: contested ones that show every feature.

This is not how the site orders stories - the site analyses most outlets first,
because that is what predicts differences (see README). A demonstration needs
something else: a handful of stories that between them exercise every part of
a story page, and that are contested enough to show why comparing coverage
matters. The exported bundle says the stories were chosen this way.

A story's features, read from its finished analysis:

    related     the coverage table has an outlet that said something close
                but not the same
    figures     outlets published different numbers for one quantity
    quotes      a remark quoted by two or more outlets
    reworded    one of those versions shortened or worded differently
    framing     two or more outlets describe a named person
    people      it names someone who has a page on the site

Contention: the share of its headlines with a critical or defensive verb
("slams", "accuses", "denies", "defends"), plus quotes reported with one.

    python -m backend.scripts.pick_showcase --analyse 30 --n 14
    python -m backend.scripts.export_review <the ids it prints> --note showcase
"""
import argparse
import re
from functools import lru_cache

import numpy as np

from backend.analysis.divergence import differences
from backend.config import CLUSTER_MIN_COHERENCE, REPORTING_VERBS
from backend.db.connection import get_cursor

CONTESTED = ("criticised", "denied or defended")


def _verb_pattern(verb):
    """'accuse' matches accuses/accused; 'hit back' only as a phrase, never bare
    'hits' - which matched "milk output hits 5.2B litres"."""
    first, _, rest = verb.partition(" ")
    stem = re.escape(first) + r"\w{0,4}"
    return stem + (r"\s+" + re.escape(rest) if rest else "")


CONFLICT = re.compile(r"\b(" + "|".join(_verb_pattern(v) for family in CONTESTED
                                       for v in REPORTING_VERBS[family]) + r")\b", re.I)
# Controversy also shows in what a headline is about, not only in who "slams"
# whom: a probe, a row, an arrest. Verbs alone left nearly every story at zero.
CONTROVERSY = re.compile(
    r"\b(rows?|disputes?|disputed|clash(es|ed)?|protests?|protesters|impeach\w*|probes?|"
    r"probed|scandals?|petitions?|arrest(s|ed)?|murder(s|ed)?|kill(s|ed|ings?)?|crackdown|"
    r"ultimatum|rift|feud|showdown|war|attacks?|attacked|standoff|outcry|backlash|fraud|"
    r"corruption|graft|sack(s|ed)?|suspend(s|ed)?|ousts?|ousted|defy|defies|condemns?|"
    r"condemned|demands?|warns?|threat(s|ens)?|bans?|banned|evict\w*|demoli\w*|"
    r"court|charged|accused|controversy|controversial|uproar|fury|anger)\b", re.I)
CONTESTED_TOPICS = {"Politics", "Security"}
FEATURES = ("related", "figures", "quotes", "reworded", "framing", "people")
# two picked stories this alike are one event told twice
SAME_EVENT = 0.75


def stories():
    """Every coherent story covered by two or more outlets, with any analysis."""
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.id, c.coherence, c.topic_label, ca.title_summary, ca.consensus,
                   ca.figure_digest, ca.framing, ca.quotes,
                   array_agg(a.title ORDER BY a.published_utc) AS titles,
                   count(DISTINCT a.source_name) AS outlets
            FROM clusters c
            JOIN cluster_members cm ON cm.cluster_id = c.id
            JOIN articles a ON a.id = cm.article_id
            LEFT JOIN cluster_analysis ca ON ca.cluster_id = c.id
            WHERE c.coherence >= %s
            GROUP BY c.id, ca.title_summary, ca.consensus, ca.figure_digest,
                     ca.framing, ca.quotes
            HAVING count(DISTINCT a.source_name) >= 2
        """, (CLUSTER_MIN_COHERENCE,))
        return cur.fetchall()


def headline_contention(story):
    """Share of headlines that report a dispute, plus a quarter for a political
    or security story."""
    disputed = sum(1 for t in story["titles"] if CONFLICT.search(t) or CONTROVERSY.search(t))
    topic = 0.25 if story.get("topic_label") in CONTESTED_TOPICS else 0.0
    return disputed / len(story["titles"]) + topic


def features(story, people_ids):
    """{feature: bool} and the contention score for an analysed story."""
    from backend.analysis.portrayal import family_of

    found = differences(story)
    remarks = story["quotes"] or []
    shared = [r for r in remarks if r["outlets"] > 1]
    framing = [f for f in story["framing"] or [] if len(f.get("sources") or []) > 1]
    speakers = {r.get("speaker_id") for r in remarks}
    flags = {
        "related": found["related"] > 0,
        "figures": found["figures"] > 0,
        "quotes": bool(shared),
        "reworded": found["quotes"] > 0,
        "framing": bool(framing),
        "people": bool(speakers & people_ids) or bool(_named(story) & people_ids),
    }
    contested_quotes = sum(1 for r in remarks for v in r["versions"]
                           if family_of(v.get("verb")) in CONTESTED)
    return flags, headline_contention(story) + 0.25 * contested_quotes, found


@lru_cache(maxsize=1)
def _nlp():
    from backend.nlp.entities import load_nlp
    return load_nlp()


def _named(story):
    return {e.ent_id_ for doc in _nlp().pipe(story["titles"]) for e in doc.ents if e.ent_id_}


def analyse_contested(all_stories, limit):
    """Run the active tier on the most contested stories not yet analysed with quotes."""
    from backend.analysis.runner import analyze_cluster

    waiting = [s for s in all_stories if s["quotes"] is None]
    waiting.sort(key=lambda s: (-headline_contention(s), -s["outlets"]))
    for i, story in enumerate(waiting[:limit], start=1):
        try:
            analyze_cluster(story["id"], refresh=True)
            print(f"  [{i}/{min(limit, len(waiting))}] analysed {story['id']}", flush=True)
        except Exception as exc:
            print(f"  [{i}] {story['id']} failed: {type(exc).__name__}: {exc}", flush=True)


def pick(n):
    from backend.nlp.embeddings import model
    from backend.nlp.entities import people

    people_ids = set(people())
    scored = []
    for story in stories():
        if story["quotes"] is None or not story["consensus"]:
            continue
        flags, contention, found = features(story, people_ids)
        # contention weighs three times a feature: a demonstration of contested
        # coverage built from weather and textbook stories would miss the point
        scored.append((sum(flags.values()) + 3 * contention + found["score"] / 4,
                       story, flags, contention, found))
    scored.sort(key=lambda t: -t[0])

    titles = [t[1]["title_summary"] or t[1]["titles"][0] for t in scored]
    vectors = model.encode(titles, normalize_embeddings=True) if titles else np.zeros((0, 384))
    chosen = []
    for i in range(len(scored)):
        if any(float(vectors[i] @ vectors[j]) >= SAME_EVENT for j in chosen):
            continue   # the same event, already chosen in another cluster
        chosen.append(i)
        if len(chosen) == n:
            break
    return [scored[i] for i in chosen], len(scored)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=14)
    parser.add_argument("--analyse", type=int, default=0,
                        help="first analyse this many contested stories not yet analysed")
    args = parser.parse_args()
    if args.analyse:
        print(f"Analysing up to {args.analyse} contested stories first...")
        analyse_contested(stories(), args.analyse)
    chosen, pool = pick(args.n)
    print(f"\nChose {len(chosen)} of {pool} analysed stories\n")
    print(f"{'id':>5} {'contest':>8} " + " ".join(f"{f:>8}" for f in FEATURES) + "  title")
    for _, story, flags, contention, _found in chosen:
        marks = " ".join(f"{'yes' if flags[f] else '-':>8}" for f in FEATURES)
        print(f"{story['id']:>5} {contention:>8.2f} {marks}  {(story['title_summary'] or '')[:60]}")
    covered = {f: sum(1 for _, _, flags, _, _ in chosen if flags[f]) for f in FEATURES}
    print("\nstories showing each feature:", covered)
    print("\nexport with:\n  python -m backend.scripts.export_review "
          + " ".join(str(s["id"]) for _, s, _, _, _ in chosen) + " --note showcase")


if __name__ == "__main__":
    main()
