"""NewsMTSC worker: targeted sentiment, run inside the NewsSentiment environment.

NewsSentiment needs Python 3.8-3.11, torch < 2.1 and transformers <= 4.24, none
of which Newseye's own environment can have, so this script runs under that
environment's interpreter and imports nothing from Newseye. targeted.py starts
it once and keeps it running, so the model loads once per process.

One JSON request per line on stdin, one JSON answer per line on stdout:

    -> {"items": [[text, start, end], ...]}
    <- {"results": [[p_negative, p_neutral, p_positive] or null, ...],
        "errors": [null or "why", ...]}

The first line written is {"ready": true, ...} once the model has loaded, or
{"ready": false, "error": "..."} if it cannot. start and end are character
offsets of the entity in text. Needs Python 3.10 or 3.11 (zip(strict=)).
"""
import json
import sys

LABELS = ("negative", "neutral", "positive")
# characters of context kept on each side of the entity when a text is too long
# for the model (150 tokens); one retry with the trimmed text before giving up
WINDOW = 300
# items scored in one vectorised pass
BATCH = 32


def write(stream, message):
    stream.write(json.dumps(message) + "\n")
    stream.flush()


def trimmed(left, right):
    """The context nearest the entity, cut at word boundaries."""
    if len(left) > WINDOW:
        left = left[-WINDOW:]
        left = left[left.find(" ") + 1:] if " " in left else left
    if len(right) > WINDOW:
        right = right[:WINDOW]
        right = right[:right.rfind(" ")] if " " in right else right
    return left, right


def as_probabilities(result):
    probability = {r["class_label"]: float(r["class_prob"]) for r in result}
    return [probability.get(label, 0.0) for label in LABELS]


def tidy(text, start, end):
    """Offsets that mark the entity without surrounding spaces (the model asserts
    on them), or None when they do not mark anything."""
    if not (0 <= start < end <= len(text)):
        return None
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def score(classifier, text, start, end):
    """([p_neg, p_neu, p_pos], None), or (None, why) when the item cannot be scored."""
    span = tidy(text, start, end)
    if span is None:
        return None, "offsets do not mark an entity in the text"
    left, target, right = text[:span[0]], text[span[0]:span[1]], text[span[1]:]
    error = None
    for attempt in range(2):
        try:
            return as_probabilities(classifier.infer(
                text_left=left, target_mention=target, text_right=right,
                disable_tqdm=True)), None
        except Exception as exc:  # the model raises on texts it cannot take
            error = f"{type(exc).__name__}: {exc}"
            if attempt == 0:
                shorter = trimmed(left, right)
                if shorter == (left, right):
                    break
                left, right = shorter
    return None, error


def score_all(classifier, items):
    """Every item in vectorised batches; item by item, with the trimmed retry, when
    a batch fails - one text the model cannot take fails its whole batch."""
    results, errors = [None] * len(items), [None] * len(items)
    spans = [tidy(text, int(start), int(end)) for text, start, end in items]
    ready = [i for i, span in enumerate(spans) if span is not None]
    for i, span in enumerate(spans):
        if span is None:
            errors[i] = "offsets do not mark an entity in the text"
    try:
        out = classifier.infer(targets=[(items[i][0], *spans[i]) for i in ready],
                               batch_size=BATCH, disable_tqdm=True)
        for i, result in zip(ready, out, strict=True):
            results[i] = as_probabilities(result)
    except Exception:
        for i in ready:
            results[i], errors[i] = score(classifier, items[i][0], *spans[i])
    return results, errors


def main():
    # torch, transformers and NewsSentiment print progress and warnings, and some
    # of it reaches the process's stdout directly rather than through sys.stdout.
    # The answers get a private copy of stdout; descriptor 1 itself is pointed at
    # stderr, so nothing else can reach the pipe the client reads.
    import os
    answers = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    try:
        from NewsSentiment import TargetSentimentClassifier
        from NewsSentiment.download import Download
        from NewsSentiment.train import OWN_MODELNAME2CLASS

        # Without its weights the model would download 584 MB on its own first
        # start, inside whatever pipeline step asked for a score; say so instead.
        weights = Download.model_path(OWN_MODELNAME2CLASS["grutsc"])
        if not os.path.isfile(weights):
            write(answers, {"ready": False, "error": (
                f"GRU-TSC weights missing at {weights}; download them once with: "
                f"{sys.executable} -m NewsSentiment download")})
            return 1
        classifier = TargetSentimentClassifier()
    except Exception as exc:
        write(answers, {"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1
    try:
        from importlib.metadata import version
        package = version("NewsSentiment")
    except Exception:
        package = "unknown"
    import torch
    write(answers, {"ready": True, "package": "NewsSentiment " + package,
                    "torch": torch.__version__,
                    "python": ".".join(map(str, sys.version_info[:3]))})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            items = json.loads(line)["items"]
        except Exception as exc:
            write(answers, {"results": [], "errors": [], "error": f"bad request: {exc}"})
            continue
        results, errors = score_all(classifier, items)
        write(answers, {"results": results, "errors": errors})
    return 0


if __name__ == "__main__":
    sys.exit(main())
