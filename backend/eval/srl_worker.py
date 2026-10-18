"""SRL worker: PropBank semantic role labelling, run inside the AllenNLP environment.

AllenNLP 2.10 needs Python <= 3.10, torch < 1.13 and spaCy < 3.4, none of which
Newseye's environment can have, so this runs under ~/.venvs/srl and imports
nothing from Newseye - the same arrangement as analysis/tsc_worker.py.

One JSON request per line on stdin, one answer per line on stdout:

    -> {"texts": ["MPs slam Ruto over the housing levy", ...]}
    <- {"results": [[{"verb": "slam", "verb_span": [4, 8],
                      "args": [{"label": "ARG0", "span": [0, 3]}, ...]}, ...], ...]}

Spans are character offsets into each text. The first line written is
{"ready": true} once the model has loaded, or {"ready": false, "error": ...}.
"""
import json
import os
import sys

ARCHIVE = os.environ.get("SRL_ARCHIVE") or os.path.join(
    os.path.expanduser("~"), ".cache", "newseye", "srl",
    "structured-prediction-srl-bert.2020.12.15.tar.gz")


def write(stream, message):
    stream.write(json.dumps(message) + "\n")
    stream.flush()


def offsets(text, words):
    """Character span of each token, found left to right in the original text."""
    spans, at = [], 0
    for word in words:
        start = text.find(word, at)
        if start < 0:                      # tokenizer normalised it: no span
            spans.append(None)
            continue
        spans.append((start, start + len(word)))
        at = start + len(word)
    return spans


def frames(text, result):
    """AllenNLP's BIO tags per verb as labelled character spans."""
    spans = offsets(text, result["words"])
    out = []
    for verb in result["verbs"]:
        args, current = [], None
        for tag, span in zip(verb["tags"], spans, strict=True):
            if span is None:
                continue
            if tag.startswith("B-"):
                current = {"label": tag[2:], "span": list(span)}
                args.append(current)
            elif tag.startswith("I-") and current is not None and current["label"] == tag[2:]:
                current["span"][1] = span[1]
            else:
                current = None
        v = next((a for a in args if a["label"] == "V"), None)
        if v is None:
            continue
        out.append({"verb": text[v["span"][0]:v["span"][1]], "verb_span": v["span"],
                    "args": [a for a in args if a["label"] != "V"]})
    return out


def main():
    answers = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    os.dup2(2, 1)            # library output to stderr; stdout is for answers only
    sys.stdout = sys.stderr
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    try:
        import allennlp_models.structured_prediction  # noqa: F401 - registers the SRL model
        from allennlp.predictors.predictor import Predictor
        predictor = Predictor.from_path(ARCHIVE)
    except Exception as exc:
        write(answers, {"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1
    write(answers, {"ready": True, "model": os.path.basename(ARCHIVE)})
    for line in sys.stdin:
        if not line.strip():
            continue
        # a byte-order mark arrives when a shell pipes text in; the client never sends one
        texts = json.loads(line.lstrip("﻿"))["texts"]
        results = []
        for text in texts:
            try:
                results.append(frames(text, predictor.predict(sentence=text)))
            except Exception as exc:
                print(f"failed on {text[:60]!r}: {exc}", file=sys.stderr)
                results.append(None)
        write(answers, {"results": results})
    return 0


if __name__ == "__main__":
    sys.exit(main())
