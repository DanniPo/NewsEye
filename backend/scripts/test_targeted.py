"""Does targeted scoring degrade safely, and do the evaluation tools count right?

The NewsMTSC model runs in an environment CI does not have, so the client is
tested against a stand-in worker that speaks the same protocol: it answers with
fixed probabilities (positive toward names starting with R, negative otherwise)
and dies on cue.

    client     answers come back in order; a missing interpreter, or a worker
               that dies mid-run, gives None for every item - never an error
    framing    with targeted scoring on, a PERSON mention with a span is scored
               toward the person; another type, a claim without spans, a stale
               span or a dead worker falls back to sentence tone, and
               scored_by says which
    claims     the spans extract_claims records point at the entities
    metrics    F1m, F1pn, accuracy, kappa, threshold tuning and the bootstrap,
               on cases worked out by hand
    sampler    outlets take turns, one text per article, two mentions per text
               at most, no outlet name on the annotators' sheet
    agree      agreed items are filled in, disagreements wait to be settled, and
               a settled label survives running agree again

    python -m backend.scripts.test_targeted
"""
import csv
import io
import os
import random
import sys
import tempfile
from contextlib import contextmanager, redirect_stdout

from backend.scripts.testkit import case, report

FAKE_WORKER = """
import json, sys
# NewsSentiment prints this to stdout before the model is ready
print("Downloading to C:/somewhere/grutsc_v1-0-0:", flush=True)
print(json.dumps({"ready": True, "package": "stand-in", "torch": "-", "python": "-"}),
      flush=True)
for line in sys.stdin:
    results = []
    for text, start, end in json.loads(line)["items"]:
        name = text[start:end]
        if name == "Crash":
            sys.exit(3)
        results.append([0.1, 0.2, 0.7] if name.startswith("R") else [0.6, 0.3, 0.1])
    print(json.dumps({"results": results, "errors": [None] * len(results)}), flush=True)
"""


@contextmanager
def worker(python):
    """The targeted client pointed at the stand-in worker (or at python, if given
    as a path that does not exist), with a fresh start and a clean exit."""
    from backend.analysis import targeted

    folder = tempfile.mkdtemp()
    script = os.path.join(folder, "fake_worker.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(FAKE_WORKER)
    saved = (targeted.NEWSMTSC_PYTHON, targeted.WORKER, targeted._worker, targeted._unavailable,
             targeted.TARGETED_CACHE, targeted._cache)
    targeted.NEWSMTSC_PYTHON, targeted.WORKER = python, script
    # a cache of its own, so a test never reads or writes the real one
    targeted.TARGETED_CACHE = os.path.join(folder, "scores.jsonl")
    targeted._worker = targeted._unavailable = targeted._cache = None
    try:
        yield targeted
    finally:
        if targeted._worker is not None:
            targeted._worker.close()
        (targeted.NEWSMTSC_PYTHON, targeted.WORKER, targeted._worker, targeted._unavailable,
         targeted.TARGETED_CACHE, targeted._cache) = saved


@contextmanager
def sentence_tone_zero():
    """Sentence tone stubbed to 0.0, so a test never loads the RoBERTa model."""
    from backend.analysis import framing
    original = framing.sentence_sentiment
    framing.sentence_sentiment = lambda sentences, batch_size=16: [0.0] * len(sentences)
    try:
        yield
    finally:
        framing.sentence_sentiment = original


def client_cases():
    rows = []
    with worker(sys.executable) as targeted:
        got = targeted.targeted_sentiment([("Ruto spoke in Kisumu.", 0, 4),
                                           ("Odinga spoke in Bondo.", 0, 6)])
        rows.append(case("[client] stray output before ready, then two items in order",
                         "[0.6, -0.5]", str(got), got == [0.6, -0.5], "FR-07"))
        best = targeted.most_likely([0.1, 0.2, 0.7])
        rows.append(case("[client] the model's own class", "positive", str(best),
                         best == "positive", "FR-07"))
        targeted._worker.close()
        targeted._worker, targeted._unavailable = None, "stopped for the test"
        again = targeted.targeted_sentiment([("Odinga spoke in Bondo.", 0, 6),
                                             ("Ruto spoke in Kisumu.", 0, 4),
                                             ("Ruto spoke in Nyeri.", 0, 4)])
        rows.append(case("[client] scored mentions served from the cache, worker stopped",
                         "[-0.5, 0.6, None]", str(again), again == [-0.5, 0.6, None],
                         "NFR-01, NFR-02"))
    with worker(sys.executable) as targeted:
        got = targeted.targeted_sentiment([("Ruto spoke.", 0, 4), ("Crash here.", 0, 5)])
        after = targeted.available()
        rows.append(case("[client] the worker dies mid-run",
                         "[None, None], then unavailable without a retry",
                         f"{got}, then {'available' if after else 'unavailable'}",
                         got == [None, None] and not after, "NFR-02"))
    with worker(os.path.join(tempfile.gettempdir(), "no-such-python.exe")) as targeted:
        got = targeted.targeted_sentiment([("Ruto spoke.", 0, 4)])
        reason = targeted.why_unavailable() or ""
        rows.append(case("[client] no NewsSentiment interpreter installed",
                         "[None], with the reason recorded", f"{got}; {reason[:60]}",
                         got == [None] and "no NewsSentiment interpreter" in reason, "NFR-02"))
    return rows


def framing_cases():
    from backend.analysis import framing

    mentions = [("Ruto spoke in Kisumu.", (0, 4), "PERSON"),
                ("KURA closed the road.", (0, 4), "ORG"),
                ("Ruto spoke in Kisumu.", None, "PERSON")]
    rows = []
    with sentence_tone_zero(), worker(sys.executable):
        got = framing.score_mentions(mentions, method="targeted")
        rows.append(case("[framing] PERSON with a span, an ORG, a PERSON without a span",
                         "targeted +0.6, sentence 0.0, sentence 0.0",
                         ", ".join(f"{how} {score:+.1f}" for score, how in got),
                         [how for _, how in got] == ["targeted", "sentence", "sentence"]
                         and got[0][0] == 0.6, "FR-07"))
    with sentence_tone_zero(), worker(os.path.join(tempfile.gettempdir(), "missing.exe")):
        got = framing.score_mentions(mentions, method="targeted")
        rows.append(case("[framing] targeted on but the model missing",
                         "sentence for all three", ", ".join(how for _, how in got),
                         all(how == "sentence" for _, how in got), "FR-07, NFR-02"))
    claim = {"text": "Raila Odinga spoke in Bondo.", "entities": [["Raila Odinga", "PERSON"]],
             "spans": [[0, 12]]}
    stale = {**claim, "text": "On Monday Raila Odinga spoke in Bondo."}
    got = (framing._span(claim, 0, "Raila Odinga"), framing._span(stale, 0, "Raila Odinga"),
           framing._span({"text": "x", "entities": [["x", "ORG"]]}, 0, "x"))
    rows.append(case("[framing] a span is used only while it still marks the entity",
                     "(0, 12), None, None", str(got), got == ((0, 12), None, None), "FR-07"))
    claims = [{"text": f"Raila Odinga met {who} in Kisumu on Monday.", "source": source,
               "entities": [["Raila Odinga", "PERSON"], ["Kisumu", "GPE"]],
               "spans": [[0, 12], [len(f"Raila Odinga met {who} in "),
                                   len(f"Raila Odinga met {who} in Kisumu")]]}
              for source in ("KBC", "Capital FM") for who in ("traders", "elders")]
    with sentence_tone_zero(), worker(sys.executable):
        from backend.analysis import framing as live
        original = live.FRAMING_SENTIMENT
        live.FRAMING_SENTIMENT = "targeted"
        try:
            records = live.analyze_framing(claims)
        finally:
            live.FRAMING_SENTIMENT = original
    raila = next((r for r in records if r["entity"] == "Raila Odinga"), None)
    got = sorted((s["source"], s["scored_by"], s["frame"]) for s in raila["sources"]) \
        if raila else None
    rows.append(case("[framing] two outlets, two mentions each, targeted on",
                     "each outlet scored_by targeted, positive",
                     str(got), got == [("Capital FM", "targeted", "positive"),
                                       ("KBC", "targeted", "positive")], "FR-07"))
    return rows


def claims_case():
    from backend.analysis.claims import extract_claims
    claims = extract_claims("President William Ruto said 12 people died in Kisumu on Tuesday. "
                            "Interior CS Kipchumba Murkomen sent 300 officers to the area.")
    wrong = [(c["text"][s:e], text) for c in claims
             for (text, _), (s, e) in zip(c["entities"], c["spans"], strict=True)
             if c["text"][s:e] != text]
    found = sum(len(c["spans"]) for c in claims)
    return case("[claims] every recorded span points at its entity",
                "all spans match", f"{found} spans, {len(wrong)} mismatched",
                found > 0 and not wrong, "FR-07")


def metric_cases():
    from backend.eval import metrics
    gold = ["negative", "neutral", "positive", "positive"]
    predicted = ["negative", "positive", "positive", "neutral"]
    got = (round(metrics.f1m(gold, predicted), 3), round(metrics.f1pn(gold, predicted), 3),
           metrics.accuracy(gold, predicted))
    rows = [case("[metrics] F1m, F1pn, accuracy on a worked example",
                 "(0.5, 0.75, 0.5)", str(got), got == (0.5, 0.75, 0.5), "FR-07")]
    k = round(metrics.kappa(["positive", "positive", "negative", "negative"],
                            ["positive", "negative", "negative", "negative"]), 3)
    rows.append(case("[metrics] Cohen's kappa: 75% agreement, 50% expected", "0.5", str(k),
                     k == 0.5, "FR-07"))
    t = metrics.tune_threshold(["neutral", "neutral", "positive", "negative"],
                               [0.2, -0.2, 0.5, -0.5])
    rows.append(case("[metrics] tuning picks the perfect band nearest 0.15",
                     "0.2", str(t), t == 0.2, "FR-07"))
    same = metrics.paired_bootstrap(gold, predicted, predicted, resamples=200)
    better = metrics.paired_bootstrap(gold * 5, predicted * 5, gold * 5, resamples=200)
    rows.append(case("[metrics] bootstrap: identical methods, then a perfect one",
                     "difference 0 with interval 0 to 0; then interval above 0",
                     f"{same[0]:+.2f} ({same[1]:+.2f} to {same[2]:+.2f}); "
                     f"then {better[1]:+.2f} to {better[2]:+.2f}",
                     same[:3] == (0.0, 0.0, 0.0) and better[1] > 0, "FR-07"))
    return rows


def sampler_cases():
    from backend.eval.sample_framing import SHEET_FIELDS, mark, select

    def text(outlet, article, mentions):
        return {"outlet": outlet, "article_id": article, "field": "headline", "url": "",
                "published": "", "text": "t", "model_text": "t",
                "mentions": [(i, i + 1, f"e{i}", "PERSON") for i in range(mentions)]}

    texts = ([text("Big", f"b{i}", 3) for i in range(20)]
             + [text("Small", "s1", 1), text("Small", "s1", 2)]   # one article, two texts
             + [text("Mid", f"m{i}", 1) for i in range(4)])
    items = select(texts, 12, random.Random(1))
    per_text = max(sum(1 for i in items if i["article_id"] == a)
                   for a in {i["article_id"] for i in items})
    outlets = {i["outlet"] for i in items}
    small = sum(1 for i in items if i["outlet"] == "Small")
    return [case("[sampler] 12 items from a big, a small and a middling outlet",
                 "all three outlets; at most 2 items per text; 1 text of the small "
                 "outlet's article", f"{sorted(outlets)}; at most {per_text} per text; "
                 f"{small} item(s) from Small",
                 outlets == {"Big", "Small", "Mid"} and per_text <= 2 and 1 <= small <= 2,
                 "FR-07"),
            case("[sampler] what an annotator sees",
                 "no outlet column; the entity in [[ ]]",
                 f"columns {SHEET_FIELDS}; {mark('Ruto spoke.', 0, 4)}",
                 "outlet" not in SHEET_FIELDS and mark("Ruto spoke.", 0, 4) == "[[Ruto]] spoke.",
                 "FR-07")]


def agree_case():
    from backend.eval import score_framing

    folder = tempfile.mkdtemp()

    def write(name, fields, rows):
        with open(os.path.join(folder, name), "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    write("sample.csv", ["item", "calibration", "split"],
          [{"item": i, "calibration": "no", "split": "test"} for i in ("F001", "F002", "F003")])
    write("sheet_A.csv", ["item", "label"], [{"item": "F001", "label": "1"},
                                             {"item": "F002", "label": "-1"},
                                             {"item": "F003", "label": "x"}])
    write("sheet_B.csv", ["item", "label"], [{"item": "F001", "label": "2"},
                                             {"item": "F002", "label": "0"},
                                             {"item": "F003", "label": "x"}])
    with redirect_stdout(io.StringIO()):
        score_framing.agree(folder)
        gold = score_framing.read(os.path.join(folder, "gold.csv"))
        first = {r["item"]: (r["status"], r["gold"]) for r in gold}
        for row in gold:
            if row["item"] == "F002":
                row["gold"] = "negative"
        write("gold.csv", list(gold[0]), gold)
        score_framing.agree(folder)
    second = {r["item"]: (r["status"], r["gold"])
              for r in score_framing.read(os.path.join(folder, "gold.csv"))}
    wanted_first = {"F001": ("agreed", "positive"), "F002": ("pending", ""),
                    "F003": ("agreed", "x")}
    return case("[agree] +1/+2 agree, -1/0 wait, x/x agree; then F002 settled",
                f"{wanted_first}; then F002 ('settled', 'negative')",
                f"{first}; then F002 {second['F002']}",
                first == wanted_first and second["F002"] == ("settled", "negative"), "FR-07")


def results():
    return (client_cases() + framing_cases() + [claims_case()] + metric_cases()
            + sampler_cases() + [agree_case()])


if __name__ == "__main__":
    sys.exit(report(results(), "targeted-sentiment cases"))
