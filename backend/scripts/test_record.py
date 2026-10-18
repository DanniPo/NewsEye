"""Run every test suite and keep the record: each case, what was expected, what came out.

    python -m backend.scripts.test_record
    python -m backend.scripts.test_record --out docs/evidence/my-record.md

Writes docs/evidence/test-record-<date>.md. The record names the commit it ran
against and says whether the working tree had uncommitted changes, so every
result can be traced to the code that produced it. Exits 1 if any case failed.
"""
import argparse
import importlib
import os
import platform
import subprocess
import sys
import time
from datetime import datetime

from backend.scripts.testkit import REQUIREMENTS, verdict

# In the order data moves through the pipeline. Each suite: its test-id prefix,
# the component, the requirement its cases trace to unless a case names its own,
# the test level and design technique, and what a pass means.
SUITES = [
    {"module": "test_cluster_ids", "prefix": "TC-CL", "component": "Clustering",
     "trace": "FR-02", "level": "Unit · white-box: one case per branch of the matching rule",
     "meaning": "A story keeps its id and page when the 7-day window is re-clustered"},
    {"module": "test_entities", "prefix": "TC-EN", "component": "NLP - names",
     "trace": "FR-03", "level": "Unit · black-box: real headline forms, plus names "
                                "that must not become people",
     "meaning": "spaCy, with the Kenyan list and title rule, tags Kenyan people, "
                "institutions and places"},
    {"module": "test_coverage", "prefix": "TC-CV", "component": "Analysis - coverage",
     "trace": "FR-04, NFR-04", "level": "Integration (MiniLM + NLI + set arithmetic) · "
                                        "black-box: hand-checked real pairs",
     "meaning": "An outlet is credited only with a fact it actually reported"},
    {"module": "test_quotes", "prefix": "TC-QT", "component": "Analysis - quotes",
     "trace": "FR-05", "level": "Unit · black-box: the attribution forms outlets use",
     "meaning": "Quotes get the right speaker, and each outlet's version of a remark "
                "is compared"},
    {"module": "test_figures", "prefix": "TC-FG", "component": "Analysis - figures",
     "trace": "FR-06", "level": "Unit · black-box: pairs that must group and pairs "
                                "that must not",
     "meaning": "Two outlets' figures are set side by side only when they count the "
                "same thing"},
    {"module": "test_casualties", "prefix": "TC-CS", "component": "Analysis - figures",
     "trace": "FR-06", "level": "Unit · black-box: rival counts and misleading pairs",
     "meaning": "Rival casualty counts are grouped; dead, injured and missing are kept "
                "apart"},
    {"module": "test_portrayal", "prefix": "TC-PT", "component": "Analysis - people",
     "trace": "FR-07", "level": "Unit · black-box: headline forms, including ones that "
                                "must not read as speech",
     "meaning": "Headlines are read for whether a person speaks, acts or is acted on"},
    {"module": "test_targeted", "prefix": "TC-TS", "component": "Analysis - targeted tone",
     "trace": "FR-07", "level": "Unit and integration · grey-box: a stand-in worker speaking "
                               "the NewsMTSC worker's protocol; hand-worked metric examples",
     "meaning": "Targeted scoring falls back safely, and the framing evaluation tools count "
                "correctly"},
    {"module": "test_divergence", "prefix": "TC-DV", "component": "Output - dashboard",
     "trace": "FR-08", "level": "Unit · black-box",
     "meaning": "'Where outlets differ most' counts only differences a reader can check"},
    {"module": "test_robustness", "prefix": "TC-RB", "component": "Edges - all stages",
     "trace": "NFR-02, NFR-03", "level": "Unit and integration · grey-box: boundary "
                                         "values from the code's thresholds; failures "
                                         "injected at known dependencies",
     "meaning": "Thresholds, failures, hostile feed content and empty input are handled "
                "as documented"},
]
DEFAULT_DIR = os.path.join("docs", "evidence")


def git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def environment():
    """The commit and machine a result came from."""
    import torch
    device = (torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU")
    dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    return {
        "commit": git("rev-parse", "--short", "HEAD") or "unknown",
        "dirty": dirty,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "device": device,
    }


def lint():
    """ruff over the backend: (findings, output). findings is None when ruff is absent."""
    try:
        run = subprocess.run([sys.executable, "-m", "ruff", "check", "backend"],
                             capture_output=True, text=True)
    except OSError:
        return None, ""
    if "No module named ruff" in run.stderr:
        return None, ""
    if run.returncode == 0:
        return 0, run.stdout.strip()
    found = [line for line in run.stdout.splitlines() if line.startswith("Found ")]
    count = int(found[0].split()[1]) if found else -1
    return count, run.stdout.strip()


def missing_packages():
    """Packages the suites need that this interpreter lacks - usually a sign that
    `python` is the system install rather than the project's .venv."""
    from importlib.util import find_spec
    needed = ("spacy", "torch", "transformers", "sentence_transformers", "hdbscan", "sklearn")
    return [name for name in needed if find_spec(name) is None]


def load_models():
    """Import torch and the models once, so no suite's time includes loading them."""
    started = time.time()
    import backend.nlp.classification  # noqa: F401 - imported to load, not used
    import backend.nlp.embeddings  # noqa: F401
    return time.time() - started


def run_suites():
    suites = []
    for suite in SUITES:
        print(f"{suite['module']}...", flush=True)
        started = time.time()
        module = importlib.import_module(f"backend.scripts.{suite['module']}")
        try:
            rows = module.results()
            error = None
        except Exception as exc:
            rows, error = [], f"{type(exc).__name__}: {exc}"
        seconds = time.time() - started
        for number, row in enumerate(rows, start=1):
            row["id"] = f"{suite['prefix']}-{number:02d}"
            row["trace"] = row.get("trace") or suite["trace"]
        counted = [r for r in rows if r["ok"] is not None]
        passed = sum(1 for r in counted if r["ok"])
        print(f"  {passed}/{len(counted)} in {seconds:.1f}s"
              + (f"  ERROR {error}" if error else ""))
        for row in rows:
            if row["ok"] is False:
                print(f"  FAIL {row['id']} {row['case'][:64]}\n       expected {row['expected']}"
                      f"\n       got      {row['actual']}")
        suites.append({**suite, "question": (module.__doc__ or "").strip().splitlines()[0],
                       "rows": rows, "passed": passed, "counted": len(counted),
                       "seconds": seconds, "error": error})
    return suites


def coverage(suites):
    """{requirement: (cases, passed)} across every suite."""
    found = {key: [0, 0] for key in REQUIREMENTS}
    for suite in suites:
        for row in suite["rows"]:
            if row["ok"] is None:
                continue
            for key in (k.strip() for k in row["trace"].split(",")):
                found[key][0] += 1
                found[key][1] += bool(row["ok"])
    return found


def cell(text):
    """Text safe inside one Markdown table cell."""
    return " ".join(str(text).split()).replace("|", "\\|")


def render(suites, env, lint_result, started, seconds, loading):
    counted = sum(s["counted"] for s in suites)
    passed = sum(s["passed"] for s in suites)
    known = sum(1 for s in suites for r in s["rows"] if r["ok"] is None)
    errors = [s for s in suites if s["error"]]
    findings, _ = lint_result
    lint_text = ("not run (ruff not installed)" if findings is None
                 else f"{findings} findings")

    tree = " (with uncommitted changes)" if env["dirty"] else ""
    lines = [
        f"# Test record - {started:%Y-%m-%d %H:%M}",
        "",
        f"Commit `{env['commit']}`{tree} · Python {env['python']} · torch {env['torch']} "
        f"on {env['device']} · {seconds:.0f}s, of which {loading:.0f}s loading models",
        "",
        f"**{passed} of {counted} cases passed** across {len(suites)} suites"
        + (f"; {known} known limitation recorded, not counted" if known else "")
        + f"; lint: {lint_text}."
        + (f" **{len(errors)} suite(s) crashed.**" if errors else ""),
        "",
        "Regenerate with `python -m backend.scripts.test_record`. Each case lists what the "
        "code should produce and what it produced on this run. The cases are realistic "
        "sentences in the forms Kenyan outlets use; many are failures found on live data "
        "and kept as regression cases once fixed.",
        "",
        "| Suite | Test IDs | Level · technique | Traces to | Passed | Time |",
        "|---|---|---|---|---|---|",
    ]
    for s in suites:
        result = f"{s['passed']}/{s['counted']}" + (" (crashed)" if s["error"] else "")
        ids = f"{s['prefix']}-01 to -{len(s['rows']):02d}" if s["rows"] else s["prefix"]
        lines.append(f"| `{s['module']}` | {ids} | {cell(s['level'])} | {s['trace']} | "
                     f"{result} | {s['seconds']:.1f}s |")
    lines.append(f"| `ruff check backend` | - | Static analysis | code quality | "
                 f"{lint_text} | |")

    lines += ["", "## Requirement coverage", "",
              "Cases giving evidence for each requirement. A requirement with no case "
              "here is evidenced elsewhere: the end-to-end record, or the evaluation.", "",
              "| Requirement | Cases | Passed |", "|---|---|---|"]
    for key, (cases, passed_here) in coverage(suites).items():
        lines.append(f"| {key}: {cell(REQUIREMENTS[key])} | {cases or '-'} | "
                     f"{passed_here if cases else '-'} |")

    for s in suites:
        lines += ["", f"## {s['component']}: `{s['module']}`", "", s["question"], "",
                  f"Level and technique: {s['level']}.", ""]
        if s["error"]:
            lines += [f"**The suite crashed:** `{cell(s['error'])}`", ""]
        lines += ["| Test ID | Traces to | Scenario | Expected | Actual | Verdict |",
                  "|---|---|---|---|---|---|"]
        for row in s["rows"]:
            lines.append(f"| {row['id']} | {row['trace']} | {cell(row['case'])} | "
                         f"{cell(row['expected'])} | {cell(row['actual'])} | "
                         f"{verdict(row)} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    missing = missing_packages()
    if missing:
        print(f"This Python ({sys.executable}) is missing {', '.join(missing)}.\n"
              "Run the tests inside the project environment:\n"
              "    .venv\\Scripts\\Activate.ps1      (Linux/macOS: source .venv/bin/activate)\n"
              "    python -m backend.scripts.test_record\n"
              "or call it directly: .venv\\Scripts\\python.exe -m backend.scripts.test_record")
        return 2

    started = datetime.now()
    mark = time.time()
    print("loading models...", flush=True)
    loading = load_models()
    suites = run_suites()
    lint_result = lint()
    env = environment()
    text = render(suites, env, lint_result, started, time.time() - mark, loading)

    out = args.out or os.path.join(DEFAULT_DIR, f"test-record-{started:%Y-%m-%d}.md")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, out)

    counted = sum(s["counted"] for s in suites)
    passed = sum(s["passed"] for s in suites)
    print(f"\n{passed}/{counted} cases passed; lint: "
          f"{'not run' if lint_result[0] is None else lint_result[0]} findings")
    print(f"Record written to {out}")
    failed = passed < counted or any(s["error"] for s in suites) or bool(lint_result[0])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
