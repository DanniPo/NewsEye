"""Are the sentences the coverage table groups as one fact really one fact?

The coverage table groups two outlets' sentences when their embeddings are close,
then asks NLI whether each says what the other says. Pairs NLI splits are shown as
"said something related". This draws pairs from real stories for a person to mark,
in full sentences and without showing what NLI decided:

    python -m backend.scripts.fact_pairs sample     # writes the sheet and a hidden key
    (mark one_fact y or n for each pair in docs/evidence/fact-pairs/sheet.csv)
    python -m backend.scripts.fact_pairs score      # writes the results

Half the sheet comes from pairs NLI kept and half from pairs it split, because it
keeps only about one in five and a plain random draw would leave a handful of kept
pairs behind the figure that matters most. The scores are weighted back to every
pair drawn from, so the sample's mix does not carry into the results. At most
MAX_PER_STORY pairs come from one story, since pairs from one story are not
independent.

Article text is read once and not kept. Only the sentences on the sheet are, as
with the quotes on the held-out sheets.
"""
import argparse
import csv
import json
import os
import random
import sys
from collections import Counter
from datetime import datetime

from backend.config import CLUSTER_MIN_COHERENCE
from backend.scripts.heldout import wilson

OUT_DIR = os.path.join("docs", "evidence", "fact-pairs")
SHEET = os.path.join(OUT_DIR, "sheet.csv")
KEY = os.path.join(OUT_DIR, "key.json")
FIELDS = ["pair", "outlet_a", "sentence_a", "outlet_b", "sentence_b", "one_fact", "note"]
MAX_PER_STORY = 3


def stories():
    """Every coherent story covered by at least two outlets."""
    from backend.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute("""
            SELECT c.id
            FROM clusters c
            JOIN cluster_members cm ON cm.cluster_id = c.id
            JOIN articles a ON a.id = cm.article_id
            WHERE c.coherence >= %s
            GROUP BY c.id
            HAVING count(DISTINCT a.source_name) >= 2
            ORDER BY c.id
        """, (CLUSTER_MIN_COHERENCE,))
        return [r["id"] for r in cur.fetchall()]


def story_pairs(story):
    """The cross-outlet pairs one story's coverage table would group, as the active
    tier builds them: article text where it could be read, otherwise the headline
    and snippet."""
    from backend.analysis.claims import extract_claims
    from backend.analysis.consensus import group_claims
    from backend.analysis.runner import load_cluster
    from backend.ingestion.fetch import fetch_many
    from backend.nlp.nli import relations

    _, articles = load_cluster(story)
    bodies = fetch_many([a["url"] for a in articles])
    claims = []
    for article, body in zip(articles, bodies, strict=True):
        text = body or f"{article['title']} {article['snippet'] or ''}"
        for claim in extract_claims(text):
            claim["source"] = article["source_name"]
            claims.append(claim)
    pairs = [(claims[seed], claims[member]) for seed, members in group_claims(claims)
             for member in members if claims[seed]["source"] != claims[member]["source"]]
    if not pairs:
        return []
    judged = relations([(a["text"], b["text"]) for a, b in pairs])
    return [{"story": story, "outlet_a": a["source"], "sentence_a": a["text"],
             "outlet_b": b["source"], "sentence_b": b["text"], "relation": verdict[0],
             "kept": verdict[0] != "different"}
            for (a, b), verdict in zip(pairs, judged, strict=True)]


def draw(pool, n, seed):
    """Half from the pairs NLI kept, the rest from those it split, at most
    MAX_PER_STORY from one story, in an order that does not show which is which."""
    rng = random.Random(seed)

    def take(rows, wanted):
        rows, chosen, per_story = list(rows), [], Counter()
        rng.shuffle(rows)
        for row in rows:
            if len(chosen) < wanted and per_story[row["story"]] < MAX_PER_STORY:
                chosen.append(row)
                per_story[row["story"]] += 1
        return chosen

    kept = take([r for r in pool if r["kept"]], n // 2)
    chosen = kept + take([r for r in pool if not r["kept"]], n - len(kept))
    rng.shuffle(chosen)
    return chosen


def estimate(rows, pool):
    """What the marks show. rows: [{"kept": bool, "one_fact": bool}]; pool: how many
    pairs NLI kept and split among all those drawn from."""
    kept = [r for r in rows if r["kept"]]
    split = [r for r in rows if not r["kept"]]
    kept_true = sum(r["one_fact"] for r in kept)
    split_true = sum(r["one_fact"] for r in split)
    real_kept = pool["kept"] * kept_true / len(kept) if kept else 0.0
    real_split = pool["split"] * split_true / len(split) if split else 0.0
    real = real_kept + real_split
    return {"kept": (kept_true, len(kept)), "split": (split_true, len(split)),
            "similarity_alone": real / ((pool["kept"] + pool["split"]) or 1),
            "real_matches_kept": real_kept / real if real else None}


def sample(n, seed):
    if os.path.exists(SHEET):
        with open(SHEET, encoding="utf-8-sig", newline="") as fh:
            if any(r["one_fact"].strip() for r in csv.DictReader(fh)):
                raise SystemExit(f"{SHEET} already has marks; move it first.")
    pool = []
    ids = stories()
    for number, story in enumerate(ids, start=1):
        found = story_pairs(story)
        pool += found
        print(f"  {number}/{len(ids)} story {story}: {len(found)} pairs", flush=True)
    counts = {"kept": sum(r["kept"] for r in pool), "split": sum(not r["kept"] for r in pool)}
    chosen = draw(pool, n, seed)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(SHEET, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for number, row in enumerate(chosen, start=1):
            writer.writerow({**row, "pair": number, "one_fact": "", "note": ""})
    with open(KEY, "w", encoding="utf-8") as fh:
        json.dump({"drawn": f"{datetime.now():%Y-%m-%d %H:%M}", "seed": seed, "stories": len(ids),
                   "pool": counts,
                   "pairs": [{"pair": number, "story": row["story"], "relation": row["relation"],
                              "kept": row["kept"]} for number, row in enumerate(chosen, start=1)]},
                  fh, indent=1)
    print(f"{len(chosen)} pairs from {len({r['story'] for r in chosen})} stories, drawn from "
          f"{len(pool)} pairs in {len(ids)} stories ({counts['kept']} kept by NLI, "
          f"{counts['split']} split).\nMark one_fact y or n in {SHEET}; keep {KEY} closed.")


def percent(k, n):
    low, high = wilson(k, n)
    return f"{k} of {n} = {k / n:.0%} ({low:.0%} to {high:.0%})"


def score():
    with open(SHEET, encoding="utf-8-sig", newline="") as fh:
        sheet = {int(r["pair"]): r["one_fact"].strip().lower() for r in csv.DictReader(fh)}
    with open(KEY, encoding="utf-8") as fh:
        key = json.load(fh)
    bad = {p: v for p, v in sheet.items() if v not in ("y", "n", "")}
    if bad:
        raise SystemExit(f"one_fact must be y or n; found {bad}")
    rows = [{"kept": p["kept"], "one_fact": sheet[p["pair"]] == "y"} for p in key["pairs"]
            if sheet.get(p["pair"])]
    if not rows:
        raise SystemExit(f"Nothing is marked yet in {SHEET}.")
    found = estimate(rows, key["pool"])
    pool = key["pool"]
    lines = [f"# Fact pairs: judged by a person - {datetime.now():%Y-%m-%d %H:%M}", "",
             f"Regenerate with `python -m backend.scripts.fact_pairs score`. {len(rows)} of "
             f"{len(key['pairs'])} pairs marked, drawn on {key['drawn']} with seed {key['seed']} "
             f"from {pool['kept'] + pool['split']} cross-outlet pairs in {key['stories']} stories. "
             f"NLI kept {pool['kept']} of those and split {pool['split']}. Half the sheet came from "
             "each, so the last two figures are weighted back to all the pairs.", "",
             "| Measure | Result |", "|---|---|"]
    if found["kept"][1]:
        lines.append(f"| Pairs NLI keeps as one fact that are one fact | {percent(*found['kept'])} |")
    if found["split"][1]:
        lines.append(f"| Pairs NLI splits that are really one fact | {percent(*found['split'])} |")
    lines.append(f"| Similarity alone: grouped pairs that are one fact, weighted | "
                 f"{found['similarity_alone']:.0%} |")
    if found["real_matches_kept"] is not None:
        lines.append(f"| Real matches NLI keeps together, weighted | "
                     f"{found['real_matches_kept']:.0%} |")
    lines += ["", "A real match NLI splits is shown as \"said something related\", not as left "
              "out, so it cannot become a false omission."]
    report = "\n".join(lines) + "\n"
    path = os.path.join("docs", "evidence", f"fact-pairs-results-{datetime.now():%Y-%m-%d}.md")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(report)
    print(report + f"\nWritten to {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    drawn = commands.add_parser("sample")
    drawn.add_argument("--n", type=int, default=30)
    drawn.add_argument("--seed", type=int, default=20261106)
    commands.add_parser("score")
    args = parser.parse_args()
    if args.command == "sample":
        sample(args.n, args.seed)
    else:
        score()
    return 0


if __name__ == "__main__":
    sys.exit(main())
