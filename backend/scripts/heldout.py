"""Held-out evaluation: accuracy on data no part of development ever saw.

The development hand-checks (README) drove the fixes, so they measure the system
on the data it was tuned on - the name list was even built from the headlines it
was scored on. This draws fresh samples from articles ingested after the code
froze, for a person to mark right or wrong, then scores the marks against
thresholds fixed before anyone labelled anything.

    python -m backend.scripts.heldout sample            # writes the labelling sheets
    (fill in the empty columns of each sheet)
    python -m backend.scripts.heldout score             # writes the results

Three tasks, each a CSV sheet in docs/evidence/heldout/ (UTF-8, opens in Excel):

    quotes     a quote and the speaker Newseye gave it. Mark correct y if the
               speaker is right, or if it is shown unattributed and the article
               does not make the speaker clear; otherwise n.
    roles      a headline or opening line and the role Newseye gave a named
               person (speaks, acts, acted on, ...). Mark correct y or n.
    names      a headline and two taggings, A and B: spaCy alone and Newseye, in
               an order shuffled per row so the labeller cannot tell which is
               which. Mark each y if every person, institution and place in the
               headline is found with the right type, and nothing else is.

The sample is seeded, so the same freeze, seed and database give the same sheets.
"""
import argparse
import csv
import json
import math
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime

from backend.config import CLUSTER_MIN_COHERENCE

# the commit after which the quote, portrayal and entity code did not change;
# anything ingested later was never seen while that code was being written
FREEZE = "2026-10-14T20:08:12+03:00"
FREEZE_COMMIT = "6841847"
OUT_DIR = os.path.join("docs", "evidence", "heldout")
# Fixed before labelling. A wrong speaker puts words in someone's mouth, so the
# bar is high; quotes the rules cannot place are shown unattributed instead. A
# role is shown beside the headline it came from, so a reader can check it. A
# missed or mistyped name drops a person from the comparison altogether.
ACCEPTANCE = {"quotes": 0.90, "roles": 0.80, "names": 0.90}
ENTITY_TYPES = {"PERSON", "ORG", "GPE", "NORP", "FAC", "LOC"}
SHEETS = {
    "quotes": ["item", "story", "outlet", "quote", "speaker_given", "how", "url",
               "correct", "right_speaker", "error", "note"],
    "roles": ["item", "person", "outlet", "field", "text", "role_given", "verb", "by",
              "url", "correct", "right_role", "note"],
    "names": ["item", "outlet", "headline", "tagging_A", "tagging_B", "A_correct",
              "B_correct", "note"],
}


def unseen_stories():
    from backend.db.connection import get_cursor
    with get_cursor() as cur:
        cur.execute("""
            SELECT c.id FROM clusters c
            JOIN cluster_members cm ON cm.cluster_id = c.id
            JOIN articles a ON a.id = cm.article_id
            WHERE c.coherence >= %s
            GROUP BY c.id
            HAVING min(a.inserted_at_utc) >= %s AND count(DISTINCT a.source_name) >= 2
            ORDER BY c.id
        """, (CLUSTER_MIN_COHERENCE, FREEZE))
        return [r["id"] for r in cur.fetchall()]


def unseen_articles():
    from backend.db.connection import get_cursor
    with get_cursor() as cur:
        cur.execute("""SELECT id, source_name, title, url FROM articles
                       WHERE inserted_at_utc >= %s ORDER BY id""", (FREEZE,))
        return cur.fetchall()


def sample_quotes(stories, rng, n):
    """Run the active tier on every unseen story, timing each, and sample its quotes."""
    from backend.analysis.runner import analyze_cluster

    pool, timings = [], []
    for index, cid in enumerate(stories, start=1):
        began = time.time()
        try:
            result = analyze_cluster(cid, refresh=True)
        except Exception as exc:
            print(f"  [{index}/{len(stories)}] story {cid} failed: {type(exc).__name__}")
            continue
        seconds = time.time() - began
        timings.append({"story": cid, "seconds": round(seconds, 2),
                        "articles": len(result["articles"]), "read": result["retrieved"]})
        print(f"  [{index}/{len(stories)}] story {cid}: {seconds:.1f}s", flush=True)
        for remark in result.get("quotes") or []:
            for version in remark["versions"]:
                pool.append({"story": cid, "outlet": version["source"],
                             "quote": version["quote"],
                             "speaker_given": version.get("speaker") or "(unattributed)",
                             "how": version.get("how"), "url": version.get("url")})
    rng.shuffle(pool)
    return pool[:n], len(pool), timings


def sample_roles(articles, rng, n):
    """Every mention of a listed person in an unseen headline or opening line."""
    from backend.analysis.portrayal import corpus_context, portray
    from backend.nlp.entities import load_nlp, people

    unseen = {a["url"] for a in articles}
    nlp, context = load_nlp(lemmas=True), corpus_context(days=3)
    pool = []
    for person, entry in people().items():
        outlets, _ = portray(person, days=3, nlp=nlp, context=context, tone=False)
        for outlet, summary in outlets.items():
            for record in summary["records"]:
                if record["url"] in unseen:
                    pool.append({"person": entry["name"], "outlet": outlet,
                                 "field": record["field"], "text": record["text"],
                                 "role_given": record["role"], "verb": record["verb"] or "",
                                 "by": record["by"] or "", "url": record["url"]})
    rng.shuffle(pool)
    return pool[:n], len(pool)


def tagging(doc, headline=None):
    """'text (TYPE); ...' in the headline's own wording.

    Newseye parses a re-cased copy with straight apostrophes, and its name list
    adds ids. Shown as parsed, either gave away which tagging was Newseye's, so
    the labeller was not blind: "Raila (PERSON: raila-odinga)" beside "Raila
    (GPE)". Both taggings now quote the headline itself and carry no ids.
    """
    source = headline if headline is not None and len(headline) == len(doc.text) else doc.text
    found = [f"{source[e.start_char:e.end_char]} ({e.label_})"
             for e in doc.ents if e.label_ in ENTITY_TYPES]
    return "; ".join(found) or "(nothing found)"


def sample_names(articles, rng, n):
    """Headlines tagged by spaCy alone and by Newseye, in a shuffled order per row."""
    import spacy

    from backend.analysis.portrayal import CURLY_POSSESSIVE, corpus_context
    from backend.config import SPACY_MODEL
    from backend.nlp.entities import load_nlp
    from backend.nlp.truecase import truecase

    chosen = rng.sample(list(articles), min(n, len(articles)))
    baseline, system = spacy.load(SPACY_MODEL), load_nlp(lemmas=True)
    lexicon = corpus_context(days=3)["lexicon"]
    rows, key = [], {}
    for index, article in enumerate(chosen, start=1):
        plain = tagging(baseline(article["title"]), article["title"])
        ours = tagging(system(CURLY_POSSESSIVE.sub("'", truecase(article["title"], lexicon))),
                       article["title"])
        newseye_first = rng.random() < 0.5
        key[index] = "A" if newseye_first else "B"
        a, b = (ours, plain) if newseye_first else (plain, ours)
        rows.append({"outlet": article["source_name"], "headline": article["title"],
                     "tagging_A": a, "tagging_B": b})
    return rows, len(articles), key


def write_sheet(name, rows):
    path = os.path.join(OUT_DIR, f"{name}.csv")
    if os.path.exists(path):
        raise SystemExit(f"{path} exists - it may hold labels. Move it aside to resample.")
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SHEETS[name])
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            writer.writerow({"item": index, **row})
    return path


def sample(seed, n_quotes, n_roles, n_names):
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = random.Random(seed)
    stories, articles = unseen_stories(), unseen_articles()
    print(f"Unseen since {FREEZE}: {len(articles)} articles, {len(stories)} multi-outlet "
          f"stories")
    print("Analysing the unseen stories...")
    quotes, quote_pool, timings = sample_quotes(stories, rng, n_quotes)
    print("Reading the unseen headlines for named people...")
    roles, role_pool = sample_roles(articles, rng, n_roles)
    names, name_pool, key = sample_names(articles, rng, n_names)
    for name, rows in (("quotes", quotes), ("roles", roles), ("names", names)):
        print(f"  wrote {write_sheet(name, rows)} ({len(rows)} items)")
    meta = {"drawn": datetime.now().isoformat(timespec="seconds"), "seed": seed,
            "freeze": FREEZE, "freeze_commit": FREEZE_COMMIT, "acceptance": ACCEPTANCE,
            "pools": {"quotes": quote_pool, "roles": role_pool, "names": name_pool},
            "stories": stories, "active_timings": timings,
            # which column of the names sheet is Newseye; read only when scoring
            "names_key": key}
    with open(os.path.join(OUT_DIR, "sample.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print("Now fill in the empty columns of each sheet, then run: "
          "python -m backend.scripts.heldout score")


def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes in n."""
    if not n:
        return 0.0, 0.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def marked(value):
    value = (value or "").strip().lower()
    return True if value in ("y", "yes", "1") else False if value in ("n", "no", "0") else None


def read_sheet(name):
    with open(os.path.join(OUT_DIR, f"{name}.csv"), encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def verdict(k, n, threshold):
    if not n:
        return "not labelled"
    low, _ = wilson(k, n)
    if k / n < threshold:
        return "FAIL"
    return "PASS" if low >= threshold else "PASS (interval reaches below the threshold)"


def score():
    with open(os.path.join(OUT_DIR, "sample.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    lines = [f"# Held-out evaluation - scored {datetime.now():%Y-%m-%d %H:%M}", "",
             f"Sample drawn {meta['drawn']} with seed {meta['seed']} from data ingested after "
             f"{meta['freeze']} (code frozen at commit `{meta['freeze_commit']}`). Thresholds "
             f"were fixed before labelling. Intervals are 95% Wilson score intervals.", "",
             "| Task | Labelled | Correct | Accuracy (95% CI) | Threshold | Verdict |",
             "|---|---|---|---|---|---|"]
    details = []
    for task in ("quotes", "roles"):
        rows = read_sheet(task)
        marks = [marked(r["correct"]) for r in rows]
        k, n = sum(m is True for m in marks), sum(m is not None for m in marks)
        low, high = wilson(k, n)
        threshold = meta["acceptance"][task]
        lines.append(f"| {task} | {n} of {len(rows)} | {k} | "
                     f"{(k / n if n else 0):.0%} ({low:.0%}-{high:.0%}) | ≥ {threshold:.0%} | "
                     f"{verdict(k, n, threshold)} |")
        errors = Counter((r.get("error") or r.get("right_role") or "unspecified").strip()
                         or "unspecified" for r, m in zip(rows, marks, strict=True)
                         if m is False)
        if task == "quotes":
            given = Counter("unattributed" if r["speaker_given"] == "(unattributed)"
                            else "attributed" for r, m in zip(rows, marks, strict=True)
                            if m is not None)
            right = Counter("unattributed" if r["speaker_given"] == "(unattributed)"
                            else "attributed" for r, m in zip(rows, marks, strict=True)
                            if m)
            details.append("Quotes by how they were shown: " + ", ".join(
                f"{kind} {right[kind]}/{given[kind]}" for kind in given) + ".")
        if errors:
            details.append(f"Errors in {task}: " + ", ".join(
                f"{what} {count}" for what, count in errors.most_common()) + ".")

    rows = read_sheet("names")
    key = {int(k): v for k, v in meta["names_key"].items()}
    pairs = []
    for row in rows:
        ours_col = key[int(row["item"])]
        other = "B" if ours_col == "A" else "A"
        ours, base = marked(row[f"{ours_col}_correct"]), marked(row[f"{other}_correct"])
        if ours is not None and base is not None:
            pairs.append((ours, base))
    n = len(pairs)
    for label, index in (("names: Newseye", 0), ("names: spaCy alone (baseline)", 1)):
        k = sum(p[index] for p in pairs)
        low, high = wilson(k, n)
        is_system = index == 0
        threshold = meta["acceptance"]["names"]
        lines.append(f"| {label} | {n} of {len(rows)} | {k} | "
                     f"{(k / n if n else 0):.0%} ({low:.0%}-{high:.0%}) | "
                     f"{f'≥ {threshold:.0%}' if is_system else 'baseline'} | "
                     f"{verdict(k, n, threshold) if is_system else '-'} |")
    only_ours = sum(1 for o, b in pairs if o and not b)
    only_base = sum(1 for o, b in pairs if b and not o)
    if only_ours + only_base:
        from scipy.stats import binomtest
        p = binomtest(only_ours, only_ours + only_base, 0.5).pvalue
        details.append(f"Names, paired on the same {n} headlines: Newseye right where spaCy "
                       f"alone was wrong in {only_ours}, the reverse in {only_base} "
                       f"(exact McNemar test p = {p:.3g}).")
    timings = sorted(t["seconds"] for t in meta.get("active_timings", []))
    if timings:
        median = timings[len(timings) // 2]
        within = sum(1 for t in timings if t <= 30)
        details.append(f"Active tier on the {len(timings)} unseen stories: median "
                       f"{median:.1f}s, slowest {timings[-1]:.1f}s; {within} of "
                       f"{len(timings)} within the 30 s requirement (NFR-01).")
    lines += [""] + [f"- {d}" for d in details]
    out = os.path.join("docs", "evidence", f"heldout-results-{datetime.now():%Y-%m-%d}.md")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWritten to {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    draw = sub.add_parser("sample")
    draw.add_argument("--seed", type=int, default=20261015)
    draw.add_argument("--quotes", type=int, default=40)
    draw.add_argument("--roles", type=int, default=40)
    draw.add_argument("--names", type=int, default=40)
    sub.add_parser("score")
    args = parser.parse_args()
    if args.command == "sample":
        sample(args.seed, args.quotes, args.roles, args.names)
    else:
        score()
    return 0


if __name__ == "__main__":
    sys.exit(main())
