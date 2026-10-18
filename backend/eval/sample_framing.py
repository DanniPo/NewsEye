"""Draw a framing sample from Newseye's own corpus for two people to label by hand.

    python -m backend.eval.sample_framing --n 300 --out eval/framing
    python -m backend.eval.sample_framing --dump-claims eval/framing/claims.jsonl
    python -m backend.eval.sample_framing --n 300 --out eval/framing --claims eval/framing/claims.jsonl

Writes to --out:

    sample.csv    every item with its metadata (outlet, field, entity type,
                  offsets, split) - keep it from the annotators
    sheet_A.csv   the items for annotator A: the text with the entity in [[ ]]
    sheet_B.csv   the same items for annotator B, to label without conferring

How items are drawn (seeded: the same corpus and seed give the same sample):

- Candidates are every headline and opening line in the database, plus claim
  sentences from --claims (body text), parsed with Newseye's Kenyan entity
  pipeline. Mentions are filtered as framing.py filters them: a framed type,
  not a headline fragment, not a corpus-wide term such as "Kenya".
- Each outlet's headlines, opening lines and body sentences take turns, so every
  outlet and every field is represented whatever its volume (53 stored body
  sentences against ten thousand headlines would otherwise never be drawn).
- 60% of items (--person-share) come from texts naming a person, the person
  taken first: targeted scoring applies to people, so they need the most
  items. The rest come from any text, so other types can be judged too.
- An article gives one text, and a text at most two items: when it names two
  or more entities, two are taken, so each is judged in the same text.
- Outlet names are not on the sheets, so expectations about an outlet cannot
  colour a label.
- The first 30 items are the calibration set both annotators label and then
  discuss. Discussed labels are not independent, so those items go to the dev
  split (used only to tune thresholds), with enough others to make 30%.

--dump-claims writes the claim sentences stored in finished analyses as JSON
lines (text, source), the input --claims expects.
"""
import argparse
import csv
import html
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

CALIBRATION = 30
DEV_SHARE = 0.3
MARKUP = re.compile(r"<[^>]*(?:>|$)")
FEED_FOOTER = re.compile(r"<p>The post <a.*", re.S)
SAMPLE_FIELDS = ["item", "split", "calibration", "outlet", "field", "article_id", "url",
                 "published", "entity", "entity_type", "start", "end", "entities_in_text",
                 "text", "model_text"]
SHEET_FIELDS = ["item", "text", "label", "notes"]


def mark(text, start, end):
    """The text with the entity in [[double brackets]]."""
    return f"{text[:start]}[[{text[start:end]}]]{text[end:]}"


def framed_mentions(doc):
    """(start, end, text, label) for every mention framing.py would score, first
    mention of each entity only."""
    from backend.analysis.framing import (
        FRAMED_ENT_TYPES,
        looks_like_entity,
        normalize_entity,
    )
    from backend.config import CORPUS_UNIVERSAL_TERMS

    found, seen = [], set()
    for ent in doc.ents:
        if ent.label_ not in FRAMED_ENT_TYPES or not looks_like_entity(ent.text):
            continue
        key = normalize_entity(ent.text)
        if len(key) < 3 or key in CORPUS_UNIVERSAL_TERMS or key in seen:
            continue
        seen.add(key)
        found.append((ent.start_char, ent.end_char, ent.text, ent.label_))
    return found


def plain(snippet):
    from backend.analysis.portrayal import DATELINE
    text = html.unescape(MARKUP.sub(" ", FEED_FOOTER.sub("", snippet or "")))
    return DATELINE.sub("", " ".join(text.split()))


def corpus_texts():
    """Every headline and opening line, as the reader sees it and as the parser reads it."""
    from backend.analysis.portrayal import CURLY_POSSESSIVE, corpus_context
    from backend.db.connection import get_cursor
    from backend.nlp.truecase import truecase

    lexicon = corpus_context()["lexicon"]
    with get_cursor() as cur:
        cur.execute("""SELECT id, source_name, title, coalesce(snippet, '') AS snippet, url,
                              published_utc FROM articles ORDER BY id""")
        rows = cur.fetchall()
    # a summary many articles share describes the feed, not the article
    repeated = {s for s, n in Counter(plain(r["snippet"]) for r in rows).items() if n >= 3}
    for row in rows:
        base = {"outlet": (row["source_name"] or "").strip(" |"), "article_id": row["id"],
                "url": row["url"], "published": str(row["published_utc"] or "")[:10]}
        parsed = CURLY_POSSESSIVE.sub("'", truecase(row["title"], lexicon))
        # sentence case changes letters, not lengths, so offsets hold for the original
        shown = row["title"] if len(parsed) == len(row["title"]) else parsed
        yield {**base, "field": "headline", "text": shown, "model_text": parsed}
        snippet = CURLY_POSSESSIVE.sub("'", plain(row["snippet"]))
        if len(snippet) >= 20 and snippet not in repeated:
            yield {**base, "field": "snippet", "text": snippet, "model_text": snippet}


def claim_texts(path):
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh):
            if not line.strip():
                continue
            claim = json.loads(line)
            text = " ".join(claim["text"].split())
            yield {"outlet": claim.get("source") or "", "field": "body",
                   "article_id": claim.get("article_id") or f"claim-{number}",
                   "url": claim.get("url") or "", "published": claim.get("published") or "",
                   "text": text, "model_text": text}


def with_mentions(texts):
    """Each text with its framed mentions, parsed in one pass."""
    from backend.nlp.entities import load_nlp

    texts = list(texts)
    nlp = load_nlp()
    for text, doc in zip(texts, nlp.pipe([t["model_text"] for t in texts], batch_size=256),
                         strict=True):
        text["mentions"] = framed_mentions(doc)
    return [t for t in texts if t["mentions"]]


def select(texts, n, rng, person_share=0.0):
    """Items from texts with mentions: one text per article, at most two mentions per
    text. A person_share of the items comes from texts naming a person, taking the
    person first; the rest from any text."""
    used, items = set(), []
    if person_share:
        named = [t for t in texts if any(m[3] == "PERSON" for m in t["mentions"])]
        items += _take_turns(named, round(n * person_share), rng, used, prefer="PERSON")
    items += _take_turns(texts, n - len(items), rng, used)
    return items[:n]


def _take_turns(texts, n, rng, used, prefer=None):
    """Each outlet's headlines, opening lines and body sentences take turns, so no
    outlet or field crowds the others out however many texts it has."""
    pools = defaultdict(list)
    for text in texts:
        if text["article_id"] not in used:
            pools[(text["outlet"], text["field"])].append(text)
    for pool in pools.values():
        rng.shuffle(pool)
    turns = sorted(pools)
    rng.shuffle(turns)
    cursor, items = Counter(), []
    while len(items) < n and turns:
        for turn in list(turns):
            pool = pools[turn]
            while cursor[turn] < len(pool) and pool[cursor[turn]]["article_id"] in used:
                cursor[turn] += 1
            if cursor[turn] >= len(pool):
                turns.remove(turn)
                continue
            text = pool[cursor[turn]]
            cursor[turn] += 1
            used.add(text["article_id"])
            mentions = text["mentions"]
            if len(mentions) <= 2:
                chosen = mentions
            elif prefer:
                first = [m for m in mentions if m[3] == prefer]
                rest = [m for m in mentions if m[3] != prefer]
                rng.shuffle(first)
                rng.shuffle(rest)
                chosen = (first + rest)[:2]
            else:
                chosen = rng.sample(mentions, 2)
            for start, end, entity, label in sorted(chosen):
                items.append({k: text[k] for k in ("outlet", "field", "article_id", "url",
                                                   "published", "text", "model_text")}
                             | {"entity": entity, "entity_type": label, "start": start,
                                "end": end, "entities_in_text": len(mentions)})
            if len(items) >= n:
                break
    return items[:n]


def assign(items, rng):
    """Shuffle, number, and split: calibration first, then dev, then test."""
    rng.shuffle(items)
    dev_size = round(DEV_SHARE * len(items))
    others = list(range(CALIBRATION, len(items)))
    dev = set(range(min(CALIBRATION, len(items)))) | set(
        rng.sample(others, max(0, min(len(others), dev_size - CALIBRATION))))
    for index, item in enumerate(items):
        item["item"] = f"F{index + 1:03d}"
        item["calibration"] = "yes" if index < CALIBRATION else "no"
        item["split"] = "dev" if index in dev else "test"
    return items


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def dump_claims(path):
    """Claim sentences stored in finished analyses, one JSON object per line."""
    from backend.db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute("SELECT consensus FROM cluster_analysis WHERE consensus IS NOT NULL")
        rows = cur.fetchall()
    seen, count = set(), 0
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            for fact in row["consensus"] or []:
                anchor = fact.get("anchor") or {}
                for claim in [anchor, *fact.get("related", [])]:
                    text = claim.get("text")
                    if text and text not in seen:
                        seen.add(text)
                        fh.write(json.dumps({"text": text, "source": claim.get("source"),
                                             "article_id": claim.get("article_id")}) + "\n")
                        count += 1
    print(f"Wrote {count} claim sentences to {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=300)
    parser.add_argument("--out", default=os.path.join("eval", "framing"))
    parser.add_argument("--seed", type=int, default=20261015)
    parser.add_argument("--claims", default=None, help="JSON lines of body sentences")
    parser.add_argument("--person-share", type=float, default=0.6,
                        help="share of items drawn from texts naming a person: targeted "
                             "scoring applies to people, so they need the most items")
    parser.add_argument("--dump-claims", default=None,
                        help="write stored claim sentences to this file and stop")
    args = parser.parse_args()
    if args.dump_claims:
        dump_claims(args.dump_claims)
        return 0
    for name in ("sample.csv", "sheet_A.csv", "sheet_B.csv"):
        if os.path.exists(os.path.join(args.out, name)):
            raise SystemExit(f"{args.out}/{name} exists and may hold labels. "
                             "Move it aside to draw a new sample.")
    rng = random.Random(args.seed)
    texts = list(corpus_texts())
    if args.claims:
        texts += list(claim_texts(args.claims))
    print(f"Parsing {len(texts):,} texts for named entities...", flush=True)
    texts = with_mentions(texts)
    items = assign(select(texts, args.n, rng, args.person_share), rng)
    os.makedirs(args.out, exist_ok=True)
    write_csv(os.path.join(args.out, "sample.csv"), SAMPLE_FIELDS, items)
    sheet = [{"item": i["item"], "text": mark(i["text"], i["start"], i["end"]),
              "label": "", "notes": ""} for i in items]
    for name in ("sheet_A.csv", "sheet_B.csv"):
        write_csv(os.path.join(args.out, name), SHEET_FIELDS, sheet)
    counts = Counter(i["outlet"] for i in items)
    print(f"{len(items)} items from {len(texts):,} texts with mentions: "
          + ", ".join(f"{k} {v}" for k, v in Counter(i["field"] for i in items).items())
          + f"; {len(counts)} outlets (fewest {min(counts.values())}, most "
          f"{max(counts.values())}); PERSON {sum(i['entity_type'] == 'PERSON' for i in items)}; "
          f"dev {sum(i['split'] == 'dev' for i in items)}, "
          f"test {sum(i['split'] == 'test' for i in items)}")
    print(f"Written to {args.out}/: sample.csv (keep from annotators), sheet_A.csv, sheet_B.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
