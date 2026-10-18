"""Targeted sentiment: the writer's attitude toward one entity, from NewsMTSC.

Sentence tone scores the whole sentence, so "Ruto condemns the killings in
Kisumu" reads negative although nothing in it is negative about Ruto. NewsMTSC's
GRU-TSC model (Hamborg & Donnay, 2021) is trained to judge the writer's attitude
toward one marked person instead.

The model needs an older torch and transformers than Newseye's environment has,
so it runs as a worker (tsc_worker.py) under NEWSMTSC_PYTHON - its own
environment - started on first use and kept for the life of the process. If the
worker cannot start, every score comes back None and callers fall back to
sentence tone: nothing breaks when the model is missing.

The model takes 1-2 s a mention on a laptop CPU and about 0.26 s on its GPU, so
every score is kept in a cache file (TARGETED_CACHE) keyed by the text, the
entity's offsets and the model version. Headlines do not change, so a site build scores only what is new, and
cached scores are served even when the worker is down.

    from backend.analysis.targeted import targeted_sentiment
    targeted_sentiment([("Ruto condemns the killings in Kisumu.", 0, 4)])
"""
import atexit
import hashlib
import json
import os
import queue
import subprocess
import threading

from backend.config import NEWSMTSC_PYTHON, TARGETED_CACHE

WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tsc_worker.py")
LOG = os.path.join("logs", "tsc_worker.log")
LABELS = ("negative", "neutral", "positive")
# the model these scores come from; a different model or version starts a fresh cache
MODEL_KEY = "NewsSentiment-1.2.28/grutsc_v1-0-0"
# the first start downloads the model weights, a few hundred MB
LOAD_TIMEOUT = 1200
ANSWER_TIMEOUT = 600
BATCH = 64

_worker = None
# why the worker could not start: not retried within the same process
_unavailable = None
_cache = None


class WorkerUnavailable(RuntimeError):
    pass


class _Worker:
    def __init__(self, python, script):
        if not python or not os.path.exists(python):
            raise WorkerUnavailable(f"no NewsSentiment interpreter at {python!r}; "
                                    "see eval/framing/README.md")
        os.makedirs(os.path.dirname(os.path.abspath(LOG)), exist_ok=True)
        self.log = open(LOG, "a", encoding="utf-8")
        # -I: isolated, so this folder's modules cannot shadow the worker's imports
        self.process = subprocess.Popen(
            [python, "-I", "-u", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.log, text=True, encoding="utf-8", bufsize=1)
        # Windows pipes cannot be read with a timeout, so a thread reads them
        self.lines = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        first = self._answer(LOAD_TIMEOUT)
        if not first or not first.get("ready"):
            self.close()
            reason = (first or {}).get("error") or "the worker exited or never answered"
            raise WorkerUnavailable(f"{reason} (log: {LOG})")
        self.info = first

    def _pump(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def _answer(self, timeout):
        """The worker's next JSON line; anything else it prints is logged and skipped."""
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
                self.log.write(f"[client] skipped non-JSON worker output: {line[:200]}")
                self.log.flush()

    def probabilities(self, items):
        self.process.stdin.write(json.dumps({"items": items}) + "\n")
        self.process.stdin.flush()
        reply = self._answer(ANSWER_TIMEOUT)
        if reply is None or len(reply.get("results", ())) != len(items):
            raise WorkerUnavailable("the worker stopped answering")
        return reply["results"]

    def close(self):
        try:
            self.process.stdin.close()
            self.process.terminate()
            self.process.wait(timeout=10)
        except Exception:
            pass
        self.log.close()


def _get_worker():
    global _worker, _unavailable
    if _worker is None and _unavailable is None:
        try:
            _worker = _Worker(NEWSMTSC_PYTHON, WORKER)
            atexit.register(_worker.close)
        except (WorkerUnavailable, OSError) as exc:
            _unavailable = str(exc)
    return _worker


def available():
    """True when the worker is running, starting it if need be."""
    return _get_worker() is not None


def why_unavailable():
    return _unavailable


def worker_info():
    """What the worker runs on: package, torch and Python versions."""
    worker = _get_worker()
    return dict(worker.info) if worker else None


def _key(text, start, end):
    return hashlib.sha1(f"{MODEL_KEY}\n{start}:{end}\n{text}".encode()).hexdigest()


def _load_cache():
    """{key: probabilities} from the cache file, read once per process."""
    global _cache
    if _cache is None:
        _cache = {}
        if TARGETED_CACHE and os.path.exists(TARGETED_CACHE):
            with open(TARGETED_CACHE, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        key, value = json.loads(line)
                        _cache[key] = value
                    except ValueError:
                        continue   # a line cut short by a crash mid-write
    return _cache


def _remember(pairs):
    if not TARGETED_CACHE or not pairs:
        return
    os.makedirs(os.path.dirname(os.path.abspath(TARGETED_CACHE)), exist_ok=True)
    with open(TARGETED_CACHE, "a", encoding="utf-8") as fh:
        for key, value in pairs:
            fh.write(json.dumps([key, value]) + "\n")


def probabilities(items):
    """[p_negative, p_neutral, p_positive] per (text, start, end), or None per item
    that could not be scored. Cached scores come back even when the model is
    unavailable; everything else is then None."""
    global _worker, _unavailable
    items = [(str(text), int(start), int(end)) for text, start, end in items]
    cache = _load_cache()
    keys = [_key(*item) for item in items]
    # each uncached mention once, however often it repeats in this call
    todo, seen = [], set()
    for i, key in enumerate(keys):
        if key not in cache and key not in seen:
            seen.add(key)
            todo.append(i)
    worker = _get_worker() if todo else None
    if worker is not None:
        try:
            for start in range(0, len(todo), BATCH):
                chunk = todo[start:start + BATCH]
                answers = worker.probabilities([items[i] for i in chunk])
                fresh = [(keys[i], p) for i, p in zip(chunk, answers, strict=True)
                         if p is not None]
                cache.update(fresh)
                _remember(fresh)
        except (WorkerUnavailable, OSError, ValueError) as exc:
            worker.close()
            _worker, _unavailable = None, f"worker failed mid-run: {exc}"
    return [cache.get(key) for key in keys]


def targeted_sentiment(items):
    """Signed attitude toward each entity, P(positive) - P(negative) in -1..1, the
    same scale as framing.sentence_sentiment; None where it could not be scored."""
    return [None if p is None else round(p[2] - p[0], 4) for p in probabilities(items)]


def most_likely(probability):
    """The model's own class for one item's probabilities."""
    if probability is None:
        return None
    return LABELS[max(range(3), key=lambda i: probability[i])]


def compare(text, name):
    """Print sentence tone beside the attitude toward one name in the text."""
    from backend.analysis.framing import _frame_label, sentence_sentiment
    from backend.config import FRAMING_TARGETED_THRESHOLD

    start = text.index(name)
    tone = sentence_sentiment([text])[0]
    p = probabilities([(text, start, start + len(name))])[0]
    info = worker_info() or {}
    print(f"text:   {text}")
    print(f"model:  {info.get('package', 'unavailable')}, torch {info.get('torch', '-')}")
    width = len(f"targeted toward {name}:") + 2
    print(f"{'sentence tone:':<{width}}{tone:+.2f}  {_frame_label(tone)}")
    if p is None:
        print(f"{f'targeted toward {name}:':<{width}}unavailable ({why_unavailable()})")
        return
    score = p[2] - p[0]
    print(f"{f'targeted toward {name}:':<{width}}{score:+.2f}  "
          f"{_frame_label(score, FRAMING_TARGETED_THRESHOLD)}")
    print("  probabilities:  " + "  ".join(f"{label} {v:.3f}"
                                           for label, v in zip(LABELS, p, strict=True)))


if __name__ == "__main__":
    import sys
    # python -m backend.analysis.targeted "Ruto condemns the killings in Kisumu." Ruto
    compare(sys.argv[1], sys.argv[2])
