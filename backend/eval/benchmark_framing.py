"""Sentence tone against targeted sentiment, on NewsMTSC's human-labelled test sets.

    python -m backend.eval.benchmark_framing              # full run, writes the report
    python -m backend.eval.benchmark_framing --limit 40   # a quick check

The question: does scoring a mention for the writer's attitude toward that
person (NewsMTSC's GRU-TSC model, via the NewsSentiment package) match human
judgement better than scoring the whole sentence's tone, as Newseye did
(cardiffnlp's Twitter RoBERTa)? NewsMTSC (Hamborg & Donnay, 2021) is the
human-labelled news benchmark for exactly that task.

Data: the dev and test splits of NewsMTSC's two test sets as used in the
authors' own experiments - "rw" (the real-world distribution of sentiment) and
"mt" (every sentence names at least two people). Downloaded from the authors'
repository into eval/framing/newsmtsc/, which is not committed: cite the paper.

Both methods read the same sentence. Each gets a neutral band tuned on dev, and
is also shown at the fixed +/-0.15 Newseye used; the targeted model is also
shown with its own most likely class. Everything reported is on test.

Caveats, repeated in the report: GRU-TSC was trained on NewsMTSC's train split,
so this is in-domain for it and out-of-domain for the sentence model (trained
on tweets). The practical question - which existing method should Newseye use
to describe how outlets present people - is a fair one to answer this way, but
the result says nothing about Kenyan text. The labelled sample in eval/framing
(sample_framing, score_framing) is what does.
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request
from collections import Counter
from datetime import datetime

from backend.eval import metrics

SOURCE = ("https://raw.githubusercontent.com/fhamborg/NewsMTSC/main/NewsSentiment/"
          "experiments/default/datasets/newsmtsc-{set}/{split}.jsonl")
DATA_DIR = os.path.join("eval", "framing", "newsmtsc")
REPORT = os.path.join("eval", "framing", "benchmark.md")
POLARITY = {2.0: "negative", 4.0: "neutral", 6.0: "positive"}
SETS = ("rw", "mt")
# Fixed before the first run. Targeted scoring replaces sentence tone for people
# only if it wins on both test sets, by more than resampling noise.
DECISION = ("Switch PERSON mentions to targeted scoring if, on both the rw and the mt "
            "test set, the targeted method with its dev-tuned threshold has a higher F1m "
            "than the sentence method with its dev-tuned threshold, and the paired 95% "
            "bootstrap interval of the difference lies wholly above zero. The production "
            "threshold is then the targeted method's, tuned on the rw dev split. A combined "
            "method (a blend of both scores, or a stacked model over both, each fitted on "
            "dev alone) replaces targeted only if it beats the dev-tuned targeted method "
            "on F1m on both test sets the same way; otherwise the single model stays, as "
            "the simpler of two equals.")

# Constructed sentences that separate the tone of an event from the attitude toward
# a person. The first four, with their labels, are the worked examples of the
# annotation guide (eval/framing/README.md); the rest were written for this check
# by the same rules. A behaviour check, not a sample of real text: never read the
# pass count as accuracy.
CHALLENGE = [
    ("Ruto condemns the killings in Kisumu.", "Ruto", {"neutral", "positive"},
     "guide: a negative event, Ruto shown responding to it"),
    ("Gachagua claims he was sidelined.", "Gachagua", {"negative"},
     "guide: 'claims' signals the writer's doubt"),
    ("Police tear-gas supporters of Kalonzo.", "Kalonzo", {"neutral"},
     "guide: done to his supporters, nothing said about him"),
    ("Raila hits back at critics over IEBC stance.", "Raila", {"neutral"},
     "guide: conflict alone is not an attitude"),
    ("Kindiki attended the burial of the flood victims in Embu.", "Kindiki", {"neutral"},
     "a sad event; nothing said about Kindiki"),
    ("Seven people died in the crash, Mbadi said.", "Mbadi", {"neutral"},
     "he reports the deaths; nothing said about him"),
    ("Residents praised Murkomen for restoring calm in Kerio Valley.", "Murkomen",
     {"positive"}, "praise for him"),
    ("Critics accused Murkomen of failing to stop the attacks in Kerio Valley.",
     "Murkomen", {"negative"}, "accusation against him"),
    ("Murkomen visited Kerio Valley on Tuesday.", "Murkomen", {"neutral"}, "a plain report"),
    ("Kalonzo praised Karua for her courage but accused Ruto of betraying voters.",
     "Karua", {"positive"}, "two people, opposite treatment: Karua praised"),
    ("Kalonzo praised Karua for her courage but accused Ruto of betraying voters.",
     "Ruto", {"negative"}, "same sentence: Ruto accused"),
    ("Wetangula thanked Sakaja for his support, while Babu Owino was booed off the stage.",
     "Sakaja", {"positive"}, "two people, opposite treatment: Sakaja thanked"),
    ("Wetangula thanked Sakaja for his support, while Babu Owino was booed off the stage.",
     "Babu Owino", {"negative"}, "same sentence: Babu Owino booed"),
]


def fetch(set_name, split):
    """The split's records, downloaded once; with the file's SHA-256."""
    path = os.path.join(DATA_DIR, set_name, f"{split}.jsonl")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        url = SOURCE.format(set=set_name, split=split)
        request = urllib.request.Request(url, headers={"User-Agent": "newseye-eval"})
        data = urllib.request.urlopen(request, timeout=120).read()
        with open(path, "wb") as fh:
            fh.write(data)
    raw = open(path, "rb").read()
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    return records, hashlib.sha256(raw).hexdigest()


def items(records):
    """One item per labelled target: the sentence, the target's offsets, its gold class."""
    out = []
    for record in records:
        sentence, targets = record["sentence_normalized"], record["targets"]
        for target in targets:
            out.append({"id": target["Input.gid"], "text": sentence, "start": target["from"],
                        "end": target["to"], "mention": target["mention"],
                        "gold": POLARITY[float(target["polarity"])],
                        "targets_in_sentence": len(targets)})
    return out


def predict(rows, cache):
    """Both methods' scores for every row, cached so the report can be redone cheaply."""
    if os.path.exists(cache):
        saved = {r["id"]: r for r in map(json.loads, open(cache, encoding="utf-8"))}
        if all(r["id"] in saved for r in rows):
            for row in rows:
                row.update({k: saved[row["id"]][k]
                            for k in ("sentence", "targeted", "probabilities")})
            return
    from backend.analysis import targeted
    from backend.analysis.framing import sentence_sentiment

    if not targeted.available():
        raise SystemExit(f"NewsMTSC worker unavailable: {targeted.why_unavailable()}")
    sentences = sorted({r["text"] for r in rows})
    tone = dict(zip(sentences, sentence_sentiment(sentences), strict=True))
    probabilities = targeted.probabilities([(r["text"], r["start"], r["end"]) for r in rows])
    with open(cache, "w", encoding="utf-8") as fh:
        for row, p in zip(rows, probabilities, strict=True):
            row["sentence"] = round(tone[row["text"]], 4)
            row["probabilities"] = p
            row["targeted"] = None if p is None else round(p[2] - p[0], 4)
            fh.write(json.dumps({k: row[k] for k in
                                 ("id", "sentence", "targeted", "probabilities")}) + "\n")


def challenge():
    """Each method's class for the constructed sentences."""
    from backend.analysis import targeted
    from backend.analysis.framing import sentence_sentiment

    rows = []
    texts = [text for text, *_ in CHALLENGE]
    tone = sentence_sentiment(texts)
    spans = [(text, text.index(target), text.index(target) + len(target))
             for text, target, *_ in CHALLENGE]
    aimed = targeted.targeted_sentiment(spans)
    for (text, target, expected, why), s, t in zip(CHALLENGE, tone, aimed, strict=True):
        rows.append({"text": text, "target": target, "expected": expected, "why": why,
                     "sentence": s, "targeted": t,
                     "sentence_class": metrics.label(s), "targeted_class": metrics.label(t)})
    return rows


def run(limit=None):
    from backend.analysis import targeted

    started = datetime.now()
    report = ["# Framing benchmark: sentence tone against targeted sentiment",
              "", f"Run {started:%Y-%m-%d %H:%M}. Regenerate with "
              "`python -m backend.eval.benchmark_framing`.", "",
              "**Decision rule, fixed before the first run.** " + DECISION, ""]
    results, verdicts, data_lines = {}, {}, []
    for set_name in SETS:
        split_rows = {}
        for split in ("dev", "test"):
            records, digest = fetch(set_name, split)
            rows = items(records)
            if limit:
                rows = rows[:limit]
            cache = os.path.join(DATA_DIR, set_name, f"preds_{split}"
                                 f"{'_limit' + str(limit) if limit else ''}.jsonl")
            print(f"{set_name} {split}: {len(rows)} targets in {len(records)} sentences",
                  flush=True)
            predict(rows, cache)
            split_rows[split] = rows
            data_lines.append(f"| {set_name} | {split} | {len(records)} | {len(rows)} | "
                              + ", ".join(f"{k} {v}" for k, v in sorted(
                                  Counter(r['gold'] for r in rows).items()))
                              + f" | `{digest[:12]}` |")
        dev, test = split_rows["dev"], split_rows["test"]
        predicted, tuned = metrics.compare_methods(dev, test, combined=True)
        gold = [r["gold"] for r in test]
        results[set_name] = {"predicted": predicted, "tuned": tuned, "gold": gold,
                             "test": test,
                             "missing": sum(1 for r in test if r["targeted"] is None)}

        names = list(predicted)
        sentence_tuned, targeted_tuned = names[2], names[3]
        diff, low, high, not_better = metrics.paired_bootstrap(
            gold, predicted[sentence_tuned], predicted[targeted_tuned])
        results[set_name]["bootstrap"] = (diff, low, high, not_better)
        verdicts[set_name] = diff > 0 and low > 0
        # each combined method against the targeted model alone
        results[set_name]["combined"] = {
            name: metrics.paired_bootstrap(gold, predicted[targeted_tuned], predicted[name],
                                           seed=1)
            for name in names[5:]}

    info = targeted.worker_info() or {}
    report += ["## Data", "",
               "NewsMTSC (Hamborg & Donnay, 2021), the dev and test splits the authors used. "
               "Gold labels are the authors' human annotations: the writer's attitude toward "
               "the marked person. *rw* follows the real-world distribution of sentiment in "
               "news; in *mt* every sentence names at least two people.", "",
               "| Set | Split | Sentences | Targets | Gold classes | SHA-256 |",
               "|---|---|---|---|---|---|"] + data_lines + [
               "", f"Sentence method: `{_sentence_model()}` in Newseye's environment. "
               f"Targeted method: GRU-TSC from {info.get('package', 'NewsSentiment')} "
               f"(torch {info.get('torch', '?')}, Python {info.get('python', '?')}) in its "
               "own environment. Both read the same sentence. Scores are P(positive) - "
               "P(negative); a threshold t gives positive above t, negative below -t.", ""]

    for set_name in SETS:
        r = results[set_name]
        title = {"rw": "rw: real-world distribution", "mt": "mt: two or more people per sentence"}
        rows = [("Method (test)", "F1m", "F1pn", "Accuracy")]
        for name, predicted in r["predicted"].items():
            s = metrics.scores(r["gold"], predicted)
            rows.append((name, f"{s['f1m']:.3f}", f"{s['f1pn']:.3f}", f"{s['acc']:.3f}"))
        diff, low, high, not_better = r["bootstrap"]
        report += [f"## {title[set_name]} (test, n = {len(r['gold'])})", ""] + metrics.table(rows) + [
            "", f"Targeted minus sentence, both dev-tuned: F1m {diff:+.3f} "
                f"(95% CI {low:+.3f} to {high:+.3f}; targeted not better in "
                f"{not_better:.1%} of 5,000 resamples). "
                f"Thresholds tuned on dev: sentence ±{r['tuned']['sentence']:.2f}, "
                f"targeted ±{r['tuned']['targeted']:.2f}. "
                f"Targets the model could not score (sentence tone used): {r['missing']}.", ""]
        report += ["Combined minus targeted alone (dev-tuned): " + "; ".join(
            f"{name.split(':')[1].split(',')[0].strip()} F1m {d:+.3f} (95% CI {lo:+.3f} to "
            f"{hi:+.3f})" for name, (d, lo, hi, _) in r["combined"].items()) + ".", ""]
        names = list(r["predicted"])
        for name in (names[2], names[3]):
            matrix = metrics.confusion(r["gold"], r["predicted"][name])
            report += [f"Confusion, {name} (rows gold, columns predicted):", "",
                       *metrics.table([("", "negative", "neutral", "positive")]
                              + [(c, *row) for c, row in zip(metrics.CLASSES, matrix,
                                                             strict=True)]), ""]
        if set_name == "mt":
            # where sentence tone must fail: two people in one sentence, treated differently
            by_sentence = {}
            for row, s_pred, t_pred in zip(r["test"], r["predicted"][names[2]],
                                           r["predicted"][names[3]], strict=True):
                by_sentence.setdefault(row["text"], []).append((row["gold"], s_pred, t_pred))
            split_gold = [v for v in by_sentence.values() if len({g for g, _, _ in v}) > 1]
            s_ok = sum(1 for v in split_gold for g, s, _ in v if g == s)
            t_ok = sum(1 for v in split_gold for g, _, t in v if g == t)
            n = sum(len(v) for v in split_gold)
            report += [f"Sentences whose people have different gold labels: {len(split_gold)} "
                       f"({n} targets). Sentence tone gives every person in a sentence the "
                       f"same class, so it can be right for at most one class per sentence: "
                       f"correct on {s_ok} of {n}; targeted correct on {t_ok} of {n}.", ""]

    decided = all(verdicts.values())
    # the blend's name carries its dev-tuned weights, which differ by set
    blend_wins = all(any(n.startswith("combined: blend") and lo > 0
                         for n, (_, lo, _, _) in results[s]["combined"].items()) for s in SETS)
    stack_wins = all(results[s]["combined"].get("combined: stacked logistic regression",
                                                (0, 0, 0, 0))[1] > 0 for s in SETS)
    report += ["## Decision", "",
               f"Targeted against sentence - rule met on rw: "
               f"**{'yes' if verdicts['rw'] else 'no'}**; on mt: "
               f"**{'yes' if verdicts['mt'] else 'no'}**. "
               + (f"**Switch PERSON mentions to targeted scoring**, threshold "
                  f"±{results['rw']['tuned']['targeted']:.2f} (tuned on rw dev)."
                  if decided else "**Keep sentence tone.**"), "",
               f"Combined against targeted alone - blend beats it on both sets: "
               f"**{'yes' if blend_wins else 'no'}**; stacked model: "
               f"**{'yes' if stack_wins else 'no'}**. "
               + ("**Adopt the winning combination.**" if (blend_wins or stack_wins)
                  else "**Keep the single targeted model**: no combination beats it by more "
                       "than resampling noise on both test sets."), ""]

    rows = challenge()
    passed_s = sum(r["sentence_class"] in r["expected"] for r in rows)
    passed_t = sum(r["targeted_class"] in r["expected"] for r in rows)
    report += ["## Behaviour check: constructed Kenyan sentences", "",
               "Built to separate the tone of an event from the attitude toward a person; "
               "the first four are the annotation guide's worked examples with its labels, "
               "the rest follow the same rules. Labels at ±0.15. Not a sample of real "
               f"text: read it as behaviour, not accuracy. Sentence tone matched "
               f"{passed_s} of {len(rows)}, targeted {passed_t} of {len(rows)}.", "",
               *metrics.table([("Text", "Person", "Expected", "Sentence", "Targeted")]
                      + [(r["text"], r["target"], " or ".join(sorted(r["expected"])),
                          f"{r['sentence_class']} ({r['sentence']:+.2f})"
                          + (" ✓" if r["sentence_class"] in r["expected"] else ""),
                          (f"{r['targeted_class']} ({r['targeted']:+.2f})"
                           if r["targeted"] is not None else "not scored")
                          + (" ✓" if r["targeted_class"] in r["expected"] else ""))
                         for r in rows]), "",
               "## Caveats", "",
               "- GRU-TSC was trained on NewsMTSC's train split: this test is in-domain for "
               "it and out-of-domain for the sentence model, which was trained on tweets. "
               "That is the practical choice Newseye faces between two existing tools, but "
               "it inflates the gap relative to Kenyan text.",
               "- NewsMTSC is US political news. Kenyan headlines, Sheng and Swahili, and "
               "local context are outside it; the labelled Kenyan sample "
               "(`eval/framing`, two annotators) is the test that answers that.",
               "- NewsMTSC discarded sentences under 50 characters, so headlines are outside "
               "its training data."]
    if limit:
        report.insert(2, f"**Quick check on the first {limit} targets of each split: not a "
                         "result.**")
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    out = REPORT if not limit else REPORT.replace(".md", f"-limit{limit}.md")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(report) + "\n")
    print("\n".join(report))
    print(f"\nWritten to {out}")
    return decided, results["rw"]["tuned"]["targeted"]


def _sentence_model():
    from backend.config import SENTIMENT_MODEL
    return SENTIMENT_MODEL


def figure(path):
    """F1m of each method on both test sets, from the cached predictions of the last
    full run (no model is loaded): a dot per test set, one row per method."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scores = {}
    for set_name in SETS:
        splits = {}
        for split in ("dev", "test"):
            rows = items(fetch(set_name, split)[0])
            cache = os.path.join(DATA_DIR, set_name, f"preds_{split}.jsonl")
            if not os.path.exists(cache):
                raise SystemExit(f"No cached predictions at {cache}: run the benchmark first.")
            predict(rows, cache)
            splits[split] = rows
        predicted, _ = metrics.compare_methods(splits["dev"], splits["test"], combined=True)
        gold = [r["gold"] for r in splits["test"]]
        names = list(predicted)
        shown = {"Sentence tone (before)": names[2], "Targeted, dev-tuned (adopted)": names[3],
                 "Targeted, its own class": names[4],
                 "Combined: stacked model": names[6]}
        for label, name in shown.items():
            scores.setdefault(label, {})[set_name] = metrics.f1m(gold, predicted[name])

    labels = list(scores)
    fig, ax = plt.subplots(figsize=(8, 3.2))
    for y, label in enumerate(labels):
        colour = "#2a78d6" if "adopted" in label else "#9aa3ad"
        rw, mt = scores[label]["rw"], scores[label]["mt"]
        ax.plot([min(rw, mt), max(rw, mt)], [y, y], color=colour, linewidth=2, zorder=1)
        ax.scatter([rw], [y], s=60, marker="o", color=colour, zorder=2,
                   label="rw: real-world mix (803 targets)" if y == 0 else None)
        ax.scatter([mt], [y], s=70, marker="D", color=colour, zorder=2,
                   label="mt: two or more people per sentence (1,034)" if y == 0 else None)
        ax.text(0.915, y, f"{rw:.3f} / {mt:.3f}", va="center", fontsize=9,
                fontweight="bold" if "adopted" in label else "normal")
    ax.set_yticks(range(len(labels)), labels)
    ax.invert_yaxis()
    ax.set_xlim(0.5, 0.9)
    ax.set_xlabel("macro F1 (F1m) on the NewsMTSC test split; higher is better")
    ax.text(0.915, -0.75, "rw / mt", fontsize=9, color="#555")
    ax.grid(axis="x", alpha=0.3)
    ax.legend(fontsize=8, loc="lower left", frameon=False)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return scores


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None,
                        help="score only the first N targets of each split (a quick check)")
    parser.add_argument("--figure", default=None,
                        help="draw the results chart from the cached predictions to this file")
    args = parser.parse_args()
    if args.figure:
        print(figure(args.figure))
        return 0
    run(args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
