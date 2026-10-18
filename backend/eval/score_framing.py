"""Agreement, predictions and the comparison report for the labelled framing sample.

    python -m backend.eval.score_framing agree   --dir eval/framing
    python -m backend.eval.score_framing predict --dir eval/framing
    python -m backend.eval.score_framing report  --dir eval/framing
    python -m backend.eval.score_framing compare --dir eval/framing

agree    Cohen's kappa between sheet_A.csv and sheet_B.csv; writes gold.csv.
         Items both annotators put in the same class are filled in. Settle the
         rest together by writing negative, neutral, positive or x in the gold
         column; running agree again keeps what was settled. Kappa is reported
         on the items labelled independently, i.e. without the 30 calibration
         items the annotators discussed.
predict  runs both methods once on every item and saves preds.csv. Keep it
         from the annotators.
report   writes report.md: F1m, F1pn and accuracy on the test split with
         thresholds tuned on dev, a paired bootstrap interval for the
         difference, subsets, confusion matrices, and errors.csv for the error
         analysis (causes already filled in are kept).
compare  needs no labels: how often the two methods put an item in different
         classes, by field and entity type, with the sharpest examples. That
         shows what switching would change - not which method is right.
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime

from backend.eval import metrics

CAUSES = ("weak", "both-valid", "target-confusion", "context", "gold-wrong",
          "headline-grammar", "kenyan-context", "none")


def read(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write(path, fields, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse(value):
    """-3..3 as an int, "x", None when empty, or "invalid"."""
    value = (value or "").strip().lower().replace("−", "-")
    if not value:
        return None
    if value == "x":
        return "x"
    try:
        number = int(float(value))
    except ValueError:
        return "invalid"
    return number if -3 <= number <= 3 and float(value) == number else "invalid"


def as_class(value):
    if value == "x" or value is None or value == "invalid":
        return value
    return "negative" if value < 0 else "positive" if value > 0 else "neutral"


def agree(folder):
    sample = {r["item"]: r for r in read(os.path.join(folder, "sample.csv"))}
    sheets = {name: {r["item"]: r for r in read(os.path.join(folder, f"sheet_{name}.csv"))}
              for name in ("A", "B")}
    settled = {r["item"]: r["gold"].strip().lower()
               for r in read(os.path.join(folder, "gold.csv"))
               if r.get("gold", "").strip().lower() in (*metrics.CLASSES, "x")}
    rows, statuses = [], Counter()
    independent, everything, weighted = ([], []), ([], []), ([], [])
    for item, meta in sample.items():
        a, b = (parse(sheets[name].get(item, {}).get("label")) for name in ("A", "B"))
        ca, cb = as_class(a), as_class(b)
        if "invalid" in (a, b):
            status, gold = "invalid", ""
        elif a is None or b is None:
            status, gold = "unlabelled", ""
        elif ca == cb:
            status, gold = "agreed", ca
        elif item in settled:
            status, gold = "settled", settled[item]
        else:
            status, gold = "pending", ""
        statuses[status] += 1
        if ca in metrics.CLASSES and cb in metrics.CLASSES:
            everything[0].append(ca)
            everything[1].append(cb)
            if meta["calibration"] == "no":
                independent[0].append(ca)
                independent[1].append(cb)
                weighted[0].append(a)
                weighted[1].append(b)
        rows.append({"item": item, "calibration": meta["calibration"], "split": meta["split"],
                     "label_A": "" if a is None else a, "label_B": "" if b is None else b,
                     "class_A": ca or "", "class_B": cb or "", "status": status,
                     "gold": gold})
    write(os.path.join(folder, "gold.csv"), ["item", "calibration", "split", "label_A",
                                             "label_B", "class_A", "class_B", "status",
                                             "gold"], rows)
    result = {
        "kappa_independent": metrics.kappa(*independent),
        "n_independent": len(independent[0]),
        "kappa_all": metrics.kappa(*everything),
        "n_all": len(everything[0]),
        "kappa_7point_quadratic": metrics.kappa(*weighted, weights="quadratic"),
        "agreement_independent": (sum(x == y for x, y in zip(*independent, strict=True))
                                  / len(independent[0]) if independent[0] else None),
        "statuses": dict(statuses),
    }
    with open(os.path.join(folder, "agreement.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)

    def show(value):
        return "-" if value is None else f"{value:.3f}"

    print(f"Cohen's kappa, three classes, items labelled independently: "
          f"{show(result['kappa_independent'])} (n = {result['n_independent']}); "
          f"all items: {show(result['kappa_all'])} (n = {result['n_all']}); "
          f"7-point quadratic: {show(result['kappa_7point_quadratic'])}")
    print("Items: " + ", ".join(f"{k} {v}" for k, v in statuses.most_common()))
    if statuses["pending"]:
        print(f"Settle the {statuses['pending']} pending items together in gold.csv "
              "(negative, neutral, positive or x), then run agree again.")
    if result["kappa_independent"] is not None and result["kappa_independent"] < 0.6:
        print("Kappa is below 0.6: revise the guide before trusting these labels.")


def predict(folder):
    from backend.analysis import targeted
    from backend.analysis.framing import sentence_sentiment
    from backend.config import SENTIMENT_MODEL

    sample = read(os.path.join(folder, "sample.csv"))
    if not targeted.available():
        raise SystemExit(f"NewsMTSC worker unavailable: {targeted.why_unavailable()}")
    texts = sorted({r["model_text"] for r in sample})
    tone = dict(zip(texts, sentence_sentiment(texts), strict=True))
    probabilities = targeted.probabilities(
        [(r["model_text"], int(r["start"]), int(r["end"])) for r in sample])
    rows = []
    for row, p in zip(sample, probabilities, strict=True):
        rows.append({"item": row["item"], "sentence_score": round(tone[row["model_text"]], 4),
                     "targeted_score": "" if p is None else round(p[2] - p[0], 4),
                     "p_negative": "" if p is None else round(p[0], 4),
                     "p_neutral": "" if p is None else round(p[1], 4),
                     "p_positive": "" if p is None else round(p[2], 4),
                     "targeted_class": targeted.most_likely(p) or ""})
    write(os.path.join(folder, "preds.csv"), list(rows[0]), rows)
    with open(os.path.join(folder, "preds_meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"run": datetime.now().isoformat(timespec="seconds"),
                   "sentence_model": SENTIMENT_MODEL, "targeted": targeted.worker_info(),
                   "unscored": sum(p is None for p in probabilities)}, fh, indent=1)
    print(f"Scored {len(rows)} items; the targeted model could not score "
          f"{sum(p is None for p in probabilities)} (sentence tone stands in for those)")


def joined(folder):
    """sample.csv rows with their predictions, as the rows metrics.compare_methods takes."""
    preds = {r["item"]: r for r in read(os.path.join(folder, "preds.csv"))}
    if not preds:
        raise SystemExit("No preds.csv: run predict first.")
    rows = []
    for row in read(os.path.join(folder, "sample.csv")):
        p = preds[row["item"]]
        probabilities = None if p["targeted_score"] == "" else [
            float(p["p_negative"]), float(p["p_neutral"]), float(p["p_positive"])]
        rows.append({**row, "sentence": float(p["sentence_score"]),
                     "targeted": None if p["targeted_score"] == "" else float(p["targeted_score"]),
                     "probabilities": probabilities})
    return rows


def marked(row):
    start, end, text = int(row["start"]), int(row["end"]), row["text"]
    return f"{text[:start]}[[{text[start:end]}]]{text[end:]}"


def subsets(row):
    """The subset rows this item belongs to in the report."""
    return [f"field: {row['field']}",
            "type: PERSON" if row["entity_type"] == "PERSON" else "type: not PERSON",
            "names one entity" if int(row["entities_in_text"]) == 1 else "names several",
            f"gold: {row['status']}"]


def report(folder):
    gold = {r["item"]: r for r in read(os.path.join(folder, "gold.csv"))}
    if not gold:
        raise SystemExit("No gold.csv: run agree first.")
    rows = []
    for row in joined(folder):
        g = gold.get(row["item"], {})
        if g.get("gold") in metrics.CLASSES:
            rows.append({**row, "gold": g["gold"], "status": g["status"]})
    dev = [r for r in rows if r["split"] == "dev"]
    test = [r for r in rows if r["split"] == "test"]
    if len(dev) < 10 or len(test) < 10:
        raise SystemExit(f"Too few settled items to report: dev {len(dev)}, test {len(test)}")
    predicted, tuned = metrics.compare_methods(dev, test)
    names = list(predicted)
    truth = [r["gold"] for r in test]
    agreement = {}
    if os.path.exists(os.path.join(folder, "agreement.json")):
        agreement = json.load(open(os.path.join(folder, "agreement.json"), encoding="utf-8"))

    lines = ["# Framing on Newseye's corpus: sentence tone against targeted sentiment", "",
             f"Run {datetime.now():%Y-%m-%d %H:%M} from `{folder}`. Gold labels: two "
             "annotators, disagreements settled together. Thresholds tuned on the dev split; "
             "everything below is on test.", ""]
    if agreement.get("kappa_independent") is not None:
        lines += [f"Agreement: Cohen's kappa {agreement['kappa_independent']:.3f} on "
                  f"{agreement['n_independent']} independently labelled items (three classes); "
                  f"{agreement['kappa_7point_quadratic']:.3f} quadratic-weighted on the "
                  "7-point scale.", ""]
    lines += [f"Items with a gold class: dev {len(dev)}, test {len(test)}. Test gold: "
              + ", ".join(f"{k} {v}" for k, v in sorted(Counter(truth).items())) + ".", ""]
    table = [("Method", "F1m", "F1pn", "Accuracy")]
    for name, values in predicted.items():
        s = metrics.scores(truth, values)
        table.append((name, f"{s['f1m']:.3f}", f"{s['f1pn']:.3f}", f"{s['acc']:.3f}"))
    lines += metrics.table(table)
    for a, b, title in ((names[0], names[1], "both at ±0.15"),
                        (names[2], names[3], "both dev-tuned"),
                        (names[0], names[4], "targeted's own class against sentence ±0.15")):
        diff, low, high, not_better = metrics.paired_bootstrap(truth, predicted[a], predicted[b])
        lines.append(f"\nTargeted minus sentence, {title}: F1m {diff:+.3f} "
                     f"(95% CI {low:+.3f} to {high:+.3f}; not better in {not_better:.1%} of "
                     "resamples).")
    lines += ["", "## Subsets (test)", "",
              "F1m per subset; under 20 items is too few to read anything into.", ""]
    groups = {}
    for index, row in enumerate(test):
        for key in subsets(row):
            groups.setdefault(key, []).append(index)
    table = [("Subset", "n", *names)]
    for key in sorted(groups):
        picks = groups[key]
        g = [truth[i] for i in picks]
        table.append((key, len(picks), *(f"{metrics.f1m(g, [predicted[n][i] for i in picks]):.3f}"
                                         for n in names)))
    lines += metrics.table(table)
    for name in (names[2], names[3]):
        matrix = metrics.confusion(truth, predicted[name])
        lines += ["", f"Confusion, {name} (rows gold, columns predicted):", "",
                  *metrics.table([("", *metrics.CLASSES)]
                                 + [(c, *m) for c, m in zip(metrics.CLASSES, matrix, strict=True)])]

    # errors of the tuned targeted method, keeping causes already filled in
    errors_path = os.path.join(folder, "errors.csv")
    causes = {r["item"]: (r.get("cause", ""), r.get("note", "")) for r in read(errors_path)}
    errors = []
    for index, row in enumerate(test):
        if predicted[names[3]][index] != row["gold"]:
            cause, note = causes.get(row["item"], ("", ""))
            errors.append({"item": row["item"], "text": marked(row), "field": row["field"],
                           "entity_type": row["entity_type"], "gold": row["gold"],
                           "targeted": predicted[names[3]][index],
                           "sentence": predicted[names[2]][index],
                           "targeted_score": row["targeted"], "sentence_score": row["sentence"],
                           "cause": cause, "note": note})
    write(errors_path, ["item", "text", "field", "entity_type", "gold", "targeted", "sentence",
                        "targeted_score", "sentence_score", "cause", "note"], errors)
    filled = Counter(e["cause"] for e in errors if e["cause"])
    lines += ["", "## Errors", "",
              f"{len(errors)} test items the tuned targeted method got wrong are in "
              f"`errors.csv`. Causes recorded so far: "
              + (", ".join(f"{k} {v}" for k, v in filled.most_common()) if filled else "none")
              + f". Categories: {', '.join(CAUSES)} (README, section 6).",
              "", f"Thresholds tuned on dev: sentence ±{tuned['sentence']:.2f}, targeted "
              f"±{tuned['targeted']:.2f}."]
    with open(os.path.join(folder, "report.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def compare(folder):
    from backend.config import FRAMING_TARGETED_THRESHOLD

    rows = joined(folder)
    threshold = FRAMING_TARGETED_THRESHOLD
    for row in rows:
        row["s_class"] = metrics.label(row["sentence"])
        score = row["targeted"] if row["targeted"] is not None else row["sentence"]
        row["t_class"] = metrics.label(score, threshold)
    differ = [r for r in rows if r["s_class"] != r["t_class"]]
    lines = ["# What switching would change: sentence tone against targeted sentiment", "",
             f"Run {datetime.now():%Y-%m-%d %H:%M} on the {len(rows)} unlabelled items in "
             f"`{folder}`. Sentence tone at ±0.15; targeted at ±{threshold:.2f}. **Not "
             "accuracy:** without labels this shows only where the methods disagree.", "",
             f"The methods put {len(differ)} of {len(rows)} items "
             f"({len(differ) / len(rows):.0%}) in different classes.", ""]
    cross = Counter((r["s_class"], r["t_class"]) for r in rows)
    lines += metrics.table([("Sentence \\ targeted", *metrics.CLASSES)]
                           + [(s, *(cross[(s, t)] for t in metrics.CLASSES))
                              for s in metrics.CLASSES])
    table = [("Subset", "Items", "Different class")]
    for key in ("field", "entity_type"):
        for value, group in sorted(Counter(r[key] for r in rows).items()):
            n = sum(1 for r in differ if r[key] == value)
            table.append((f"{key}: {value}", group, f"{n} ({n / group:.0%})"))
    lines += ["", *metrics.table(table), "", "## Sharpest disagreements", ""]
    sharpest = sorted(differ, key=lambda r: -abs(
        (r["targeted"] if r["targeted"] is not None else r["sentence"]) - r["sentence"]))[:15]
    lines += metrics.table([("Text", "Sentence", "Targeted")] + [
        (marked(r).replace("|", "/"), f"{r['s_class']} ({r['sentence']:+.2f})",
         f"{r['t_class']} ({r['targeted']:+.2f})" if r["targeted"] is not None else "not scored")
        for r in sharpest])
    with open(os.path.join(folder, "compare.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["agree", "predict", "report", "compare"])
    parser.add_argument("--dir", default=os.path.join("eval", "framing"))
    args = parser.parse_args()
    {"agree": agree, "predict": predict, "report": report, "compare": compare}[args.command](
        args.dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
