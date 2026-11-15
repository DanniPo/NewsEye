"""Fine-tune GRU-TSC on Kenyan news, and judge whether the tuned weights should
replace the published ones.

    python -m backend.eval.finetune_framing pool    --n 400
    python -m backend.eval.finetune_framing build   --run r1
    python -m backend.eval.finetune_framing train   --run r1
    python -m backend.eval.finetune_framing compare --run r1

Everything lives in --dir (eval/framing/finetune):

pool     draws person mentions to label for training: pool.csv (metadata - keep
         it from the annotator) and sheet.csv (the text with the person in
         [[ ]]; label it by the annotation guide in eval/framing/README.md). No
         article or text in the evaluation sample (eval/framing/sample.csv) is
         drawn, so the evaluation stays unseen. Run it again to add items to the
         same sheet; labels already written are kept. --polar-share of the items
         come from mentions the current model scores as positive or negative:
         most mentions are neutral, and a training set of neutral mentions
         teaches the model little. compare retunes the neutral band on the
         evaluation sample's natural mix, so the oversampling does not carry
         into production.
build    turns the labelled sheet into NewsMTSC's format in
         experiments/<run>/datasets/kenya/: train and dev split by article
         (85/15), x and blank labels left out. test.jsonl is NewsMTSC's rw test
         set, so the trainer's own test score shows what the model forgot.
train    fine-tunes from the published weights (newsmtsc_train.py, under
         NEWSMTSC_PYTHON), keeps the checkpoint with the best dev F1m and deletes
         the run's other checkpoints (612 MB each).
compare  runs the published and the tuned weights on the evaluation sample's
         PERSON items and on NewsMTSC's rw and mt test sets, applies DECISION
         and writes compare-<run>.md.

experiments/ holds the weights and the training text: it stays out of git.
"""
import argparse
import csv
import glob
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter

from backend.eval import metrics
from backend.eval.score_framing import as_class, parse

FOLDER = os.path.join("eval", "framing", "finetune")
SAMPLE = os.path.join("eval", "framing", "sample.csv")
CLAIMS = os.path.join("eval", "framing", "claims.jsonl")
LAUNCHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "newsmtsc_train.py")
DATASET = "kenya"
POOL_FIELDS = ["item", "drawn", "predicted", "outlet", "field", "article_id", "url",
               "published", "entity", "entity_type", "start", "end", "entities_in_text",
               "text", "model_text"]
SHEET_FIELDS = ["item", "text", "label", "notes"]
DEV_SHARE = 0.15
# fewer labelled test items than this and compare reports no verdict
MIN_TEST = 50
# how far F1m on a NewsMTSC test set may fall before the tuning counts as forgetting
FORGETTING = 0.03
# Fixed before the first tuned model was scored.
DECISION = ("Use the tuned weights if, on the PERSON items of the Kenyan test split, "
            "their F1m at a threshold tuned on the Kenyan dev split is higher than the "
            "published weights' at theirs, the paired 95% bootstrap interval of the "
            "difference lies wholly above zero, and on neither NewsMTSC test set (rw, mt) "
            f"does their F1m (the model's own class) fall more than {FORGETTING:.2f} below "
            "the published weights'. Otherwise the published weights stay.")
PROGRESS = re.compile(r"loss: \d|> recall_avg|>> saved|dev during training|"
                      r"training finished|Error|Traceback")


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


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_dir(folder, run):
    return os.path.join(folder, "experiments", run)


def pool(folder, n, polar_share, seed, sample_path, claims):
    """Add n person mentions, from articles not yet used, to pool.csv and sheet.csv."""
    from backend.eval.sample_framing import (
        _take_turns,
        claim_texts,
        corpus_texts,
        mark,
        with_mentions,
    )

    pool_path, sheet_path = os.path.join(folder, "pool.csv"), os.path.join(folder, "sheet.csv")
    existing, sheet = read(pool_path), read(sheet_path)
    evaluation = read(sample_path)
    if not evaluation:
        raise SystemExit(f"No evaluation sample at {sample_path}: without it the training "
                         "items could overlap the items the model is judged on.")
    used = {r["article_id"] for r in evaluation + existing}
    seen = {r["model_text"] for r in evaluation + existing}
    texts = list(corpus_texts())
    if claims and os.path.exists(claims):
        texts += list(claim_texts(claims))
    # a syndicated text counts once, under whichever article comes first
    unique = {}
    for text in texts:
        if str(text["article_id"]) not in used and text["model_text"] not in seen:
            unique.setdefault(text["model_text"], text)
    print(f"Parsing {len(unique):,} texts for named entities...", flush=True)
    people = []
    for text in with_mentions(list(unique.values())):
        mentions = [m for m in text["mentions"] if m[3] == "PERSON"]
        if mentions:
            people.append(text | {"mentions": mentions})
    # a new draw each time the pool grows, the same draw for the same pool
    rng = random.Random(f"{seed}-{len(existing)}")
    candidates = _take_turns(people, n * 3 if polar_share else n, rng, set(),
                             prefer="PERSON")
    for item in candidates:
        item["drawn"], item["predicted"] = "any", ""
    chosen = candidates[:n]
    if polar_share:
        from backend.analysis import targeted
        from backend.config import FRAMING_TARGETED_THRESHOLD

        if not targeted.available():
            raise SystemExit(f"NewsMTSC worker unavailable ({targeted.why_unavailable()}); "
                             "run with --polar-share 0 to draw without it.")
        print(f"Scoring {len(candidates)} candidates to find polar ones...", flush=True)
        scores = targeted.targeted_sentiment(
            [(c["model_text"], c["start"], c["end"]) for c in candidates])
        for item, score in zip(candidates, scores, strict=True):
            item["predicted"] = "" if score is None else score
        polar = [c for c in candidates
                 if c["predicted"] != "" and abs(c["predicted"]) > FRAMING_TARGETED_THRESHOLD]
        rest = [c for c in candidates if all(c is not x for x in polar)]
        take = min(len(polar), round(n * polar_share))
        for item in polar[:take]:
            item["drawn"] = "polar"
        chosen = polar[:take] + rest[:n - take]
    rng.shuffle(chosen)
    for number, item in enumerate(chosen, start=len(existing) + 1):
        item["item"] = f"T{number:04d}"
    os.makedirs(folder, exist_ok=True)
    # the sheet first: it is the file most likely to be open in a spreadsheet
    write(sheet_path, SHEET_FIELDS, sheet + [
        {"item": i["item"], "text": mark(i["text"], i["start"], i["end"]), "label": "",
         "notes": ""} for i in chosen])
    write(pool_path, POOL_FIELDS, existing + chosen)
    drawn = Counter(i["drawn"] for i in chosen)
    print(f"Added {len(chosen)} items ({drawn['polar']} predicted polar, {drawn['any']} any) "
          f"from {len({i['article_id'] for i in chosen})} articles; "
          f"{len(existing) + len(chosen)} in the pool.")
    print(f"Label {sheet_path} (-3..3 or x, as in the annotation guide); keep pool.csv "
          "from the annotator.")


def labelled_items(folder):
    """The pool's items with a label from sheet.csv, and counts of those left out."""
    meta = {r["item"]: r for r in read(os.path.join(folder, "pool.csv"))}
    items, left_out, invalid = [], Counter(), []
    for row in read(os.path.join(folder, "sheet.csv")):
        value = parse(row.get("label"))
        if value is None or value == "x":
            left_out["unlabelled" if value is None else "x"] += 1
        elif value == "invalid":
            invalid.append(row["item"])
        elif row["item"] in meta:
            items.append(meta[row["item"]] | {"label": value})
    if invalid:
        raise SystemExit("Labels are -3..3 or x; fix " + ", ".join(invalid[:20])
                         + (" ..." if len(invalid) > 20 else ""))
    return items, left_out


def record(item):
    """One labelled mention in NewsMTSC's format: polarity 1..7, labels -3..3 shifted by 4."""
    text, start, end = item["model_text"], int(item["start"]), int(item["end"])
    return {"primary_gid": item["item"], "sentence_normalized": text,
            "targets": [{"Input.gid": item["item"], "from": start, "to": end,
                         "mention": text[start:end], "polarity": float(item["label"] + 4)}]}


def build(folder, run, seed):
    from backend.eval.benchmark_framing import fetch

    target = run_dir(folder, run)
    if os.path.exists(target):
        raise SystemExit(f"{target} exists: name a new run so earlier runs stay as they were.")
    items, left_out = labelled_items(folder)
    if not items:
        raise SystemExit(f"No labelled items in {folder}/sheet.csv yet.")
    articles = sorted({i["article_id"] for i in items})
    random.Random(seed).shuffle(articles)
    dev_articles = set(articles[:round(len(articles) * DEV_SHARE)])
    splits = {"train": [i for i in items if i["article_id"] not in dev_articles],
              "dev": [i for i in items if i["article_id"] in dev_articles]}
    data = os.path.join(target, "datasets", DATASET)
    os.makedirs(data)
    for split, rows in splits.items():
        write_jsonl(os.path.join(data, f"{split}.jsonl"), [record(r) for r in rows])
    write_jsonl(os.path.join(data, "test.jsonl"), fetch("rw", "test")[0])
    for split, rows in splits.items():
        classes = Counter(as_class(r["label"]) for r in rows)
        print(f"{split:<5} {len(rows):>4} mentions: "
              + ", ".join(f"{c} {classes[c]}" for c in metrics.CLASSES))
    print(f"test  NewsMTSC rw test (what the model forgot); left out: "
          f"{left_out['x']} x, {left_out['unlabelled']} unlabelled")
    smallest = min(Counter(as_class(r["label"]) for r in splits["train"]).get(c, 0)
                   for c in ("negative", "positive"))
    if smallest < 100:
        print(f"Only {smallest} training mentions in the smaller polar class: expect little "
              "change until there are a few hundred of each.")
    print(f"Written to {data}/")


def published_weights():
    from backend.config import NEWSMTSC_PYTHON

    code = ("from NewsSentiment.download import Download\n"
            "from NewsSentiment.train import OWN_MODELNAME2CLASS\n"
            "print(Download.model_path(OWN_MODELNAME2CLASS['grutsc']))")
    out = subprocess.run([NEWSMTSC_PYTHON, "-I", "-c", code], capture_output=True,
                         text=True, check=False)
    path = (out.stdout.strip().splitlines() or [""])[-1]
    if out.returncode or not os.path.isfile(path):
        raise SystemExit(f"Published GRU-TSC weights not found ({path or out.stderr[-300:]}); "
                         "see eval/framing/README.md, step 1.")
    return path


def train(folder, run, epochs, learning_rate, batch, seed):
    from backend.config import NEWSMTSC_PYTHON

    target = os.path.abspath(run_dir(folder, run))
    if not os.path.exists(os.path.join(target, "datasets", DATASET, "train.jsonl")):
        raise SystemExit(f"No training data in {target}: run build --run {run} first.")
    checkpoints = os.path.join(target, "state_dict")
    if glob.glob(os.path.join(checkpoints, "*")):
        raise SystemExit(f"{run} is already trained: build a new run to train again.")
    start = published_weights()
    command = [NEWSMTSC_PYTHON, "-I", LAUNCHER, "--own_model_name", "grutsc",
               "--dataset_name", DATASET, "--experiment_path", target + "/",
               "--state_dict", start, "--num_epoch", str(epochs), "--batch_size", str(batch),
               "--learning_rate", str(learning_rate), "--seed", str(seed), "--log_step", "50"]
    log = os.path.join(target, "train.log")
    print(f"Training {run} from {os.path.basename(start)}; full log in {log}", flush=True)
    with open(log, "w", encoding="utf-8") as fh:
        process = subprocess.Popen(command, cwd=target, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors="replace")
        for line in process.stdout:
            fh.write(line)
            if PROGRESS.search(line):
                print("  " + line.split("|: ", 1)[-1].rstrip(), flush=True)
        code = process.wait()
    saved = sorted(glob.glob(os.path.join(checkpoints, "*")), key=os.path.getmtime)
    if code or not saved:
        raise SystemExit(f"Training failed (exit {code}); see {log}")
    # each checkpoint is saved when dev F1m improves, so the newest is the best
    best = saved[-1]
    for path in saved[:-1]:
        os.remove(path)
    with open(os.path.join(target, "experiment_results.jsonl"), encoding="utf-8") as fh:
        stats = [json.loads(line) for line in fh if line.strip()][-1]
    summary = {"weights": best, "started_from": start, "epochs": epochs,
               "learning_rate": learning_rate, "batch_size": batch, "seed": seed,
               "dev_f1m": stats["dev_stats"]["f1_macro"],
               "newsmtsc_rw_test_f1m": stats["test_stats"]["f1_macro"]}
    with open(os.path.join(target, "train.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print(f"Best checkpoint: {best}")
    print(f"Dev F1m {summary['dev_f1m']:.3f}; NewsMTSC rw test F1m "
          f"{summary['newsmtsc_rw_test_f1m']:.3f}. Next: compare --run {run}")


def evaluation_items(sample_path):
    """The evaluation sample's PERSON items with a class: gold.csv where it has one,
    otherwise annotator A's sheet (provisional: one annotator)."""
    folder = os.path.dirname(sample_path)
    gold = {r["item"]: r["gold"] for r in read(os.path.join(folder, "gold.csv"))
            if r.get("gold") in metrics.CLASSES}
    source = "gold.csv"
    if not gold:
        gold = {r["item"]: as_class(parse(r.get("label")))
                for r in read(os.path.join(folder, "sheet_A.csv"))}
        gold = {k: v for k, v in gold.items() if v in metrics.CLASSES}
        source = "sheet_A.csv - one annotator, so provisional"
    items = [r | {"gold": gold[r["item"]]} for r in read(sample_path)
             if r["entity_type"] == "PERSON" and r["item"] in gold]
    return items, source


def score(weights, rows):
    """[p_negative, p_neutral, p_positive] or None per (text, start, end), from a
    worker on these weights (None: the published ones), and what it ran on."""
    from backend.analysis import targeted
    from backend.config import NEWSMTSC_PYTHON

    env = {k: v for k, v in os.environ.items() if k != "NEWSMTSC_STATE_DICT"}
    if weights:
        env["NEWSMTSC_STATE_DICT"] = weights
    try:
        worker = targeted._Worker(NEWSMTSC_PYTHON, targeted.WORKER, env=env)
    except targeted.WorkerUnavailable as exc:
        raise SystemExit(f"NewsMTSC worker unavailable: {exc}") from None
    try:
        out = []
        for start in range(0, len(rows), targeted.BATCH):
            out += worker.probabilities(rows[start:start + targeted.BATCH])
        return out, worker.info
    finally:
        worker.close()


def signed(p):
    return 0.0 if p is None else p[2] - p[0]


def own_class(p):
    from backend.analysis.targeted import most_likely
    return most_likely(p) or "neutral"


def compare(folder, run, sample_path, resamples):
    from backend.config import FRAMING_TARGETED_THRESHOLD
    from backend.eval.benchmark_framing import SETS, fetch, items

    info_path = os.path.join(run_dir(folder, run), "train.json")
    if not os.path.exists(info_path):
        raise SystemExit(f"{run} has no trained weights: run train --run {run} first.")
    with open(info_path, encoding="utf-8") as fh:
        trained = json.load(fh)
    kenya, source = evaluation_items(sample_path)
    dev = [i for i in kenya if i["split"] == "dev"]
    test = [i for i in kenya if i["split"] == "test"]
    if not dev or not test:
        raise SystemExit(f"The evaluation sample has {len(dev)} labelled PERSON dev items "
                         f"and {len(test)} test items; label sheet_A.csv first.")
    benchmark = {name: items(fetch(name, "test")[0]) for name in SETS}
    rows = [(i["model_text"], int(i["start"]), int(i["end"])) for i in dev + test]
    for name in SETS:
        rows += [(r["text"], r["start"], r["end"]) for r in benchmark[name]]
    scored, info = {}, {}
    for name, weights in (("published", None), ("tuned", trained["weights"])):
        print(f"Scoring {len(rows):,} items with the {name} weights...", flush=True)
        scored[name], info[name] = score(weights, rows)

    gold_dev, gold_test = [i["gold"] for i in dev], [i["gold"] for i in test]
    result = {}
    for name, p in scored.items():
        p_dev, p_test = p[:len(dev)], p[len(dev):len(dev) + len(test)]
        threshold = metrics.tune_threshold(gold_dev, [signed(x) for x in p_dev],
                                           prefer=FRAMING_TARGETED_THRESHOLD)
        predicted = [metrics.label(signed(x), threshold) for x in p_test]
        offset, forgetting = len(dev) + len(test), {}
        for set_name in SETS:
            gold = [r["gold"] for r in benchmark[set_name]]
            chunk = p[offset:offset + len(gold)]
            offset += len(gold)
            forgetting[set_name] = metrics.f1m(gold, [own_class(x) for x in chunk])
        result[name] = {"threshold": threshold, "predicted": predicted,
                        "test": metrics.scores(gold_test, predicted),
                        "own": metrics.f1m(gold_test, [own_class(x) for x in p_test]),
                        "confusion": metrics.confusion(gold_test, predicted),
                        "newsmtsc": forgetting,
                        "unscored": sum(x is None for x in p)}
    difference, low, high, not_better = metrics.paired_bootstrap(
        gold_test, result["published"]["predicted"], result["tuned"]["predicted"],
        resamples=resamples)
    drops = {s: result["published"]["newsmtsc"][s] - result["tuned"]["newsmtsc"][s]
             for s in SETS}
    if len(test) < MIN_TEST:
        verdict = (f"No verdict: {len(test)} labelled PERSON test items, fewer than "
                   f"{MIN_TEST}. Label more of the evaluation sample first.")
    elif difference > 0 and low > 0 and all(d <= FORGETTING for d in drops.values()):
        verdict = "Use the tuned weights."
    else:
        reasons = []
        if not (difference > 0 and low > 0):
            reasons.append("the Kenyan gain is not clear of resampling noise")
        reasons += [f"F1m on NewsMTSC {s} fell by {d:.3f}" for s, d in drops.items()
                    if d > FORGETTING]
        verdict = "Keep the published weights: " + "; ".join(reasons) + "."
    if "provisional" in source and verdict.startswith("Use"):
        verdict += " Provisional until the test labels are agreed by two annotators."

    def row(name):
        r = result[name]
        return (name, f"±{r['threshold']:.2f}", f"{r['test']['f1m']:.3f}",
                f"{r['test']['f1pn']:.3f}", f"{r['test']['acc']:.3f}", f"{r['own']:.3f}")

    classes = Counter(gold_test)
    lines = [f"# Fine-tuned GRU-TSC against the published weights: run {run}", "",
             f"Tuned weights: `{trained['weights']}`, from `{os.path.basename(trained['started_from'])}`, "
             f"{trained['epochs']} epochs, learning rate {trained['learning_rate']}, batch "
             f"{trained['batch_size']}, seed {trained['seed']}. Worker: "
             f"{info['tuned'].get('package')}, torch {info['tuned'].get('torch')}.", "",
             f"**Decision rule.** {DECISION}", "", f"**Verdict.** {verdict}", "",
             "## Kenyan evaluation sample, PERSON items", "",
             f"Labels from {source}. Thresholds tuned on {len(dev)} dev items; scored on "
             f"{len(test)} test items (" + ", ".join(f"{c} {classes[c]}" for c in metrics.CLASSES)
             + ").", ""]
    lines += metrics.table([("Weights", "Threshold (dev)", "F1m", "F1pn", "Accuracy",
                             "F1m, own class"), row("published"), row("tuned")])
    lines += ["", f"Difference in F1m (tuned − published): {difference:+.3f}, 95% interval "
              f"{low:+.3f} to {high:+.3f}; tuned not better in {not_better:.1%} of "
              f"{resamples:,} resamples.", "",
              "Confusion on test (rows gold, columns predicted: negative, neutral, positive):", ""]
    for name in ("published", "tuned"):
        lines.append(f"- {name}: " + " / ".join(" ".join(f"{v:>3}" for v in r)
                                                 for r in result[name]["confusion"]))
    lines += ["", "## What the tuning forgot: NewsMTSC test sets", "",
              "F1m of the model's own class, as the NewsMTSC paper reports it.", ""]
    lines += metrics.table([("Test set", "Items", "Published", "Tuned", "Change")] + [
        (s, len(benchmark[s]), f"{result['published']['newsmtsc'][s]:.3f}",
         f"{result['tuned']['newsmtsc'][s]:.3f}", f"{-drops[s]:+.3f}") for s in SETS])
    unscored = {n: r["unscored"] for n, r in result.items() if r["unscored"]}
    if unscored:
        lines += ["", "Items the model could not score count as neutral: "
                  + ", ".join(f"{n} {c}" for n, c in unscored.items()) + "."]
    if verdict.startswith("Use"):
        lines += ["", "## To switch", "",
                  f"- `NEWSMTSC_STATE_DICT={trained['weights']}` in the environment (or `.env`)",
                  f"- `FRAMING_TARGETED_THRESHOLD = {result['tuned']['threshold']:.2f}` in "
                  "`backend/config.py`",
                  "- Scores from the new weights start a fresh cache, so the next site build "
                  "rescores every headline once."]
    path = os.path.join(folder, f"compare-{run}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Kenyan test F1m: published {result['published']['test']['f1m']:.3f}, tuned "
          f"{result['tuned']['test']['f1m']:.3f} ({difference:+.3f}, 95% interval "
          f"{low:+.3f} to {high:+.3f}); NewsMTSC change: "
          + ", ".join(f"{s} {-d:+.3f}" for s, d in drops.items()))
    print(verdict)
    print(f"Written to {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", default=FOLDER)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("pool", help="draw person mentions to label for training")
    p.add_argument("--n", type=int, default=400)
    p.add_argument("--polar-share", type=float, default=0.5)
    p.add_argument("--seed", type=int, default=20261023)
    p.add_argument("--sample", default=SAMPLE, help="the evaluation sample to keep out")
    p.add_argument("--claims", default=CLAIMS, help="JSON lines of body sentences")
    b = commands.add_parser("build", help="labelled sheet to NewsMTSC's format")
    b.add_argument("--run", required=True)
    b.add_argument("--seed", type=int, default=20261023)
    t = commands.add_parser("train", help="fine-tune from the published weights")
    t.add_argument("--run", required=True)
    t.add_argument("--epochs", type=int, default=3)
    t.add_argument("--learning-rate", type=float, default=2e-5)
    # 4 fits the laptop's 4 GB GPU at the model's 150 tokens
    t.add_argument("--batch", type=int, default=4)
    t.add_argument("--seed", type=int, default=20261023)
    c = commands.add_parser("compare", help="published against tuned weights")
    c.add_argument("--run", required=True)
    c.add_argument("--sample", default=SAMPLE)
    c.add_argument("--resamples", type=int, default=5000)
    args = parser.parse_args()
    if args.command == "pool":
        pool(args.dir, args.n, args.polar_share, args.seed, args.sample, args.claims)
    elif args.command == "build":
        build(args.dir, args.run, args.seed)
    elif args.command == "train":
        train(args.dir, args.run, args.epochs, args.learning_rate, args.batch, args.seed)
    else:
        compare(args.dir, args.run, args.sample, args.resamples)
    return 0


if __name__ == "__main__":
    sys.exit(main())
