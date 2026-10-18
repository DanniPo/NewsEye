"""Portrayal roles: the hand-written rules against PropBank semantic role labelling.

    python -m backend.eval.compare_roles run      # both methods, agreement, the sheet
    (mark each row of eval/roles/disagreements.csv)
    python -m backend.eval.compare_roles score    # which method was right more often

portrayal.py reads a person's role in a headline (speaks, acts, acted on,
described, spoken about, mentioned) with rules over spaCy's dependency parse.
Semantic role labelling (SRL) is the standard model for "who did what to whom":
AllenNLP's BERT SRL model, trained on PropBank-annotated OntoNotes, run as a
worker in its own environment (srl_worker.py) because it needs old libraries.

What is compared, fixed before the first run:

- The hybrid keeps portrayal's quote and colon-headline handling ("Ruto: We
  will...", a name inside quoted words) and replaces only the grammar step,
  grammatical_role() and its headline-verb fallback, with SRL. Those are the
  parts SRL claims to do better; no SRL model knows Kenyan headline forms.
- A person's role is read from the smallest SRL argument containing the name:
  ARG0 of a speech verb -> speaks; ARG0 of any other verb -> acts; ARG1 to
  ARG4 -> acted on (by the frame's ARG0), or described when the verb is a
  copula; a name buried inside a longer argument -> spoken about when the verb
  reports speech, else mentioned; a modifier or no frame -> mentioned.
- Test sets: the 18 portrayal test cases (written for the rules, so they favour
  them), and 300 real headline and opening-line mentions drawn at random.
- Decision: only mentions where the two methods disagree can change which is
  better, so only those are labelled, blind (A and B shuffled). The hybrid
  replaces the rules only if it is right more often on them with an exact
  McNemar p < 0.05; otherwise the rules stay.
"""
import argparse
import csv
import json
import os
import queue
import random
import subprocess
import sys
import threading
from collections import Counter
from datetime import datetime

OUT = os.path.join("eval", "roles")
SRL_PYTHON = os.environ.get("SRL_PYTHON") or os.path.join(
    os.path.expanduser("~"), ".venvs", "srl", "Scripts" if os.name == "nt" else "bin",
    "python.exe" if os.name == "nt" else "python")
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "srl_worker.py")
SAMPLE = 300
SEED = 20261016
# an argument at most this many characters longer than the name is the person
# (with their titles); a longer one is a clause that merely contains the name
HEAD_SLACK = 30
ARGUMENTS = ("ARG1", "ARG2", "ARG3", "ARG4")


class SRL:
    """The SRL worker, started once and fed batches of texts."""

    def __init__(self):
        if not os.path.exists(SRL_PYTHON):
            raise SystemExit(f"No SRL environment at {SRL_PYTHON}")
        os.makedirs("logs", exist_ok=True)
        self.log = open(os.path.join("logs", "srl_worker.log"), "a", encoding="utf-8")
        self.process = subprocess.Popen(
            [SRL_PYTHON, "-I", "-u", WORKER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.log, text=True, encoding="utf-8", bufsize=1)
        self.lines = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        ready = self._answer(900)
        if not ready or not ready.get("ready"):
            raise SystemExit(f"SRL worker did not start: {(ready or {}).get('error')}")

    def _pump(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def _answer(self, timeout):
        while True:
            try:
                line = self.lines.get(timeout=timeout)
            except queue.Empty:
                return None
            if not line:
                return None
            try:
                return json.loads(line)
            except ValueError:
                continue

    def frames(self, texts, batch=16):
        out = []
        for i in range(0, len(texts), batch):
            self.process.stdin.write(json.dumps({"texts": texts[i:i + batch]}) + "\n")
            self.process.stdin.flush()
            reply = self._answer(1800)
            if reply is None:
                raise SystemExit("SRL worker stopped answering")
            out += reply["results"]
            print(f"  SRL {min(i + batch, len(texts))}/{len(texts)}", flush=True)
        return out

    def close(self):
        self.process.stdin.close()
        self.process.terminate()
        self.log.close()


def srl_role(doc, start, end, frames):
    """(role, verb, by) for the name at [start, end) from SRL frames."""
    from backend.analysis.portrayal import COPULAS, family_of

    best = None
    for frame in frames or []:
        for arg in frame["args"]:
            s, e = arg["span"]
            if s <= start and end <= e and (best is None or e - s < best[0]):
                best = (e - s, frame, arg)
    if best is None:
        return "mentioned", None, None
    size, frame, arg = best
    vs = frame["verb_span"][0]
    token = next((t for t in doc if t.idx <= vs < t.idx + len(t)), None)
    lemma = (token.lemma_ if token is not None else frame["verb"]).lower()
    agent = next((a for a in frame["args"] if a["label"] == "ARG0"), None)
    by = doc.text[agent["span"][0]:agent["span"][1]] if agent else None
    is_head = size <= (end - start) + HEAD_SLACK
    if arg["label"] == "ARG0":
        if not is_head:
            return "mentioned", None, None
        return ("speaks" if family_of(lemma) else "acts"), lemma, None
    if arg["label"] in ARGUMENTS:
        if not is_head:
            return ("spoken about", lemma, by) if family_of(lemma) else ("mentioned", None, None)
        if lemma in COPULAS and arg["label"] == "ARG1":
            return "described", lemma, None
        return "acted on", lemma, by
    return "mentioned", None, None


def rules_decided(record):
    """True when portrayal's quote or colon handling decided the role, which the
    hybrid keeps; False when the grammar step decided it."""
    from backend.analysis.portrayal import QUOTED
    return record["role"] == "spoken about" or record["verb"] == QUOTED


def describe(role, verb, by):
    detail = ", ".join(x for x in (verb and f"verb {verb}", by and f"by {by}") if x)
    return f"{role} ({detail})" if detail else role


def test_cases(nlp, srl):
    """The portrayal test cases: expected role against each method's role."""
    from backend.analysis.portrayal import CURLY_POSSESSIVE, mentions
    from backend.nlp.truecase import build_casing_lexicon, truecase
    from backend.scripts import test_portrayal as t

    lexicon = build_casing_lexicon(t.LEXICON_SOURCE, min_count=1)
    cases = ([(text, person, wanted["role"], text) for text, person, wanted in t.CASES]
             + [(text, person, "not speaks", text) for text, person in t.NOT_SPEAKING]
             + [(text, person, wanted["role"], truecase(text, lexicon))
                for text, person, wanted in t.TITLE_CASE])
    texts = [CURLY_POSSESSIVE.sub("'", parsed) for _, _, _, parsed in cases]
    docs = list(nlp.pipe(texts))
    frames = srl.frames(texts)
    rows = []
    for (text, person, wanted, _), doc, fr in zip(cases, docs, frames, strict=True):
        found = mentions(doc, person)
        if not found:
            rows.append((text, wanted, "not found", "not found"))
            continue
        m = found[0]
        hybrid = (m["role"] if rules_decided(m)
                  else srl_role(doc, m["start"], m["end"], fr)[0])
        rows.append((text, wanted, m["role"], hybrid))
    return rows


def corpus_sample(nlp):
    """SAMPLE real mentions of listed people in headlines and opening lines."""
    from backend.analysis.portrayal import corpus_context, portray
    from backend.nlp.entities import people

    context = corpus_context()
    records = []
    for person, entry in people().items():
        outlets, _ = portray(person, nlp=nlp, context=context, tone=False)
        for outlet, summary in outlets.items():
            for record in summary["records"]:
                records.append({**record, "person": entry["name"], "outlet": outlet})
    rng = random.Random(SEED)
    rng.shuffle(records)
    print(f"  {len(records):,} mentions in the corpus; sampling {SAMPLE}", flush=True)
    return records[:SAMPLE], len(records)


def marked(record):
    text, start, end = record["model_text"], record["start"], record["end"]
    shown = record["text"] if len(record["text"] or "") == len(text) else text
    return f"{shown[:start]}[[{shown[start:end]}]]{shown[end:]}"


def run():
    from backend.eval.metrics import table
    from backend.nlp.entities import load_nlp

    os.makedirs(OUT, exist_ok=True)
    sheet_path = os.path.join(OUT, "disagreements.csv")
    if os.path.exists(sheet_path):
        raise SystemExit(f"{sheet_path} exists and may hold labels: move it aside to rerun.")
    nlp = load_nlp(lemmas=True)
    print("Starting the SRL worker (AllenNLP, CPU)...", flush=True)
    srl = SRL()
    print("Test cases...", flush=True)
    cases = test_cases(nlp, srl)
    print("Sampling real mentions...", flush=True)
    sample, pool = corpus_sample(nlp)
    docs = list(nlp.pipe([r["model_text"] for r in sample]))
    frames = srl.frames([r["model_text"] for r in sample])
    srl.close()

    rows = []
    for record, doc, fr in zip(sample, docs, frames, strict=True):
        rules = (record["role"], record["verb"], record["by"])
        hybrid = rules if rules_decided(record) else srl_role(doc, record["start"],
                                                              record["end"], fr)
        rows.append({"record": record, "rules": rules, "hybrid": hybrid,
                     "kept": rules_decided(record)})

    def ok(wanted, got):
        return got != "speaks" if wanted == "not speaks" else got == wanted

    rules_ok = sum(ok(w, r) for _, w, r, _ in cases)
    hybrid_ok = sum(ok(w, h) for _, w, _, h in cases)
    differ = [r for r in rows if r["rules"][0] != r["hybrid"][0]]
    rng = random.Random(SEED + 1)
    key, sheet = {}, []
    for number, row in enumerate(differ, start=1):
        hybrid_first = rng.random() < 0.5
        key[number] = "A" if hybrid_first else "B"
        a, b = (row["hybrid"], row["rules"]) if hybrid_first else (row["rules"], row["hybrid"])
        sheet.append({"item": number, "person": row["record"]["person"],
                      "field": row["record"]["field"], "text": marked(row["record"]),
                      "option_A": describe(*a), "option_B": describe(*b),
                      "right": "", "note": ""})
    with open(sheet_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(sheet[0]) if sheet else ["item"])
        writer.writeheader()
        writer.writerows(sheet)
    with open(os.path.join(OUT, "sample.json"), "w", encoding="utf-8") as fh:
        json.dump({"run": datetime.now().isoformat(timespec="seconds"), "seed": SEED,
                   "pool": pool, "sample": len(rows), "key": key}, fh, indent=1)

    cross = Counter((r["rules"][0], r["hybrid"][0]) for r in rows if not r["kept"])
    roles = sorted({k for pair in cross for k in pair})
    by_field = Counter(r["record"]["field"] for r in differ)
    fields = Counter(r["record"]["field"] for r in rows)
    lines = ["# Portrayal roles: rules against PropBank SRL", "",
             f"Run {datetime.now():%Y-%m-%d %H:%M}. SRL: AllenNLP BERT SRL "
             "(structured-prediction-srl-bert, PropBank/OntoNotes), CPU, own environment. "
             "Regenerate with `python -m backend.eval.compare_roles run`.", "",
             "## Portrayal test cases", "",
             f"Rules {rules_ok} of {len(cases)}, hybrid with SRL {hybrid_ok} of {len(cases)}. "
             "The cases were written for the rules, so this favours them; it shows where "
             "SRL fails on headline forms the rules were built for.", "",
             *table([("Headline", "Expected", "Rules", "Hybrid (SRL)")]
                    + [(t.replace("|", "/"), w, r + ("" if ok(w, r) else " ✗"),
                        h + ("" if ok(w, h) else " ✗")) for t, w, r, h in cases]),
             "", f"## {len(rows)} real mentions (drawn from {pool:,})", "",
             f"Quote and colon handling decided {sum(r['kept'] for r in rows)} of them, the same "
             f"for both. Of the {sum(not r['kept'] for r in rows)} decided by the grammar step, "
             f"the methods agree on {sum(not r['kept'] for r in rows) - len(differ)} and differ "
             f"on {len(differ)} ({len(differ) / max(1, sum(not r['kept'] for r in rows)):.0%}): "
             + ", ".join(f"{k} {v} of {fields[k]}" for k, v in by_field.items())
             + ". Agreement says nothing about which is right; the labelled disagreements do.",
             "", "Rules (rows) against the hybrid (columns), grammar-step mentions only:", "",
             *table([("rules \\ hybrid", *roles)]
                    + [(a, *(cross[(a, b)] for b in roles)) for a in roles]),
             "", "## To finish", "",
             f"Mark `right` in `eval/roles/disagreements.csv` for each of the {len(differ)} rows: "
             "A, B, both or neither, judging only the marked person's role. The sheet does "
             "not say which option is which method. Then run "
             "`python -m backend.eval.compare_roles score`."]
    with open(os.path.join(OUT, "report.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def score():
    from scipy.stats import binomtest

    key = {int(k): v for k, v in json.load(
        open(os.path.join(OUT, "sample.json"), encoding="utf-8"))["key"].items()}
    with open(os.path.join(OUT, "disagreements.csv"), encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    hybrid_wins = rules_wins = both = neither = unlabelled = 0
    for row in rows:
        mark = row["right"].strip().upper()
        hybrid_letter = key[int(row["item"])]
        if mark == hybrid_letter:
            hybrid_wins += 1
        elif mark in ("A", "B"):
            rules_wins += 1
        elif mark == "BOTH":
            both += 1
        elif mark == "NEITHER":
            neither += 1
        else:
            unlabelled += 1
    decided = hybrid_wins + rules_wins
    p = binomtest(hybrid_wins, decided, 0.5).pvalue if decided else 1.0
    better = hybrid_wins > rules_wins and p < 0.05
    text = (f"Labelled {len(rows) - unlabelled} of {len(rows)} disagreements. Hybrid (SRL) right "
            f"where the rules were wrong: {hybrid_wins}; rules right where SRL was wrong: "
            f"{rules_wins}; both acceptable {both}; neither {neither}. Exact McNemar "
            f"p = {p:.3g}. Decision: "
            + ("switch the grammar step to SRL." if better
               else "keep the rules (SRL not shown better)."))
    with open(os.path.join(OUT, "report.md"), "a", encoding="utf-8") as fh:
        fh.write(f"\n## Result ({datetime.now():%Y-%m-%d %H:%M})\n\n{text}\n")
    print(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["run", "score"])
    args = parser.parse_args()
    if args.command == "run":
        run()
    else:
        score()
    return 0


if __name__ == "__main__":
    sys.exit(main())
