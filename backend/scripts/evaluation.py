"""Evaluation evidence: accuracy with intervals, performance and reliability over repeated runs.

    python -m backend.scripts.evaluation

Reads the development hand-checks recorded below, every passive run in
logs/passive.log, and the clusters in the database, and writes
docs/evidence/evaluation-<date>.md with the figures in docs/figures/.

The hand-checks are development samples: each one was taken while the code was
being fixed, so it measures the system on data that shaped it. The held-out
results (heldout.py) are the ones that measure it on data it never saw.
"""
import math
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime

from backend.scripts.heldout import wilson

LOG = os.path.join("logs", "passive.log")
OUT = os.path.join("docs", "evidence")
FIGURES = os.path.join("docs", "figures")
# the commit that fixed the scheduled task's priority and stage timings
OPTIMISED = "2026-09-30"
PASSIVE_LIMIT = 300   # NFR-01, seconds

# (task, measure, baseline, (k, n) before, (k, n) after, note). Counts given as a
# percentage in the original output are reconstructed from it and say so.
DEV_SAMPLES = [
    ("Kenyan names in headlines", "listed names tagged correctly",
     "spaCy alone", (136, 522), (512, 522),
     "Same 522 mentions before and after; in-sample, because the list was built from "
     "this corpus. Counts reconstructed from 26% and 98%."),
    ("Kenyan names in headlines", "unlisted names after a title tagged as people",
     "without the title rule", (84, 102), (95, 102), "12 gained, 1 lost."),
    ("Coverage table", "cross-outlet pairs grouped as one fact that are one fact",
     "similarity alone", (13, 30), (29, 30),
     "Same 30 pairs; false omissions 0 after."),
    ("Quote speakers", "speaker right, first sample", None, None, (24, 30),
     "Successive samples after successive fixes."),
    ("Quote speakers", "speaker right, second sample (attributed)", None, None, (19, 21), ""),
    ("Quote speakers", "speaker right, third sample (attributed)", None, None, (25, 26),
     "One disputed case counted as wrong."),
    ("Portrayal", "role right for a headline mention", None, None, (34, 40),
     "Random sample of 40."),
    ("Story summaries", "summaries with every name spelled right",
     "abstractive model", (72, 149), None,
     "Replaced by an extractive headline, which copies names and cannot misspell them."),
]
ORDERING = {"rho": 0.40, "n": 63, "p": 0.001}


def fisher_interval(rho, n, z=1.96):
    centre, spread = math.atanh(rho), z / math.sqrt(n - 3)
    return math.tanh(centre - spread), math.tanh(centre + spread)


def parse_runs(path=LOG):
    """One dict per passive run: when, wall seconds, stage times, failures."""
    text = open(path, encoding="utf-8", errors="replace").read()
    # each run starts with its header; the stage times and any failures come
    # after its "done in" line, so a run is everything up to the next header
    parts = re.split(r"=== Newseye passive tier \| (\S+ \S+) ===", text)
    runs = []
    for when, body in zip(parts[1::2], parts[2::2], strict=True):
        done = re.search(r"=== done in ([\d.]+)s(?: \(([\d.]+)s of it working\))?", body)
        if not done:
            continue   # cut off mid-run: the machine shut down
        tail = body[done.end():]
        stages = {name: float(sec) for name, sec in re.findall(
            r"(model load|ingest|cluster|summaries) ([\d.]+)s", tail.split("corpus:")[0])}
        runs.append({
            "when": datetime.strptime(when, "%Y-%m-%d %H:%M"),
            "wall": float(done.group(1)),
            "work": float(done.group(2)) if done.group(2) else None,
            "feeds_failed": re.findall(r"^(.+?): FEED FAILED \((.+?)\)", body, re.M),
            "run_failures": re.findall(r"^  - (.+)$", tail.split("FAILURES:")[1], re.M)
            if "FAILURES:" in tail else [],
            "stages": stages,
        })
    return runs


def describe(values):
    values = sorted(values)
    q = statistics.quantiles(values, n=20) if len(values) > 1 else values * 19
    return {"n": len(values), "median": statistics.median(values), "q1": q[4], "q3": q[14],
            "p95": q[18], "max": values[-1],
            "within": sum(1 for v in values if v <= PASSIVE_LIMIT)}


def coherences():
    from backend.db.connection import get_cursor
    with get_cursor() as cur:
        cur.execute("SELECT coherence, article_count FROM clusters WHERE coherence IS NOT NULL")
        return cur.fetchall()


def figure_runtime(runs, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates
    import matplotlib.pyplot as plt
    import matplotlib.ticker

    fig, ax = plt.subplots(figsize=(8, 3.6))
    cut = datetime.fromisoformat(OPTIMISED)
    for subset, colour, label in (([r for r in runs if r["when"] < cut], "#c2410c",
                                   f"before {OPTIMISED}"),
                                  ([r for r in runs if r["when"] >= cut], "#1d4ed8",
                                   "after")):
        ax.scatter([r["when"] for r in subset], [r["wall"] for r in subset], s=12,
                   color=colour, label=f"{label} (n={len(subset)})")
    ax.axhline(PASSIVE_LIMIT, color="#555", linestyle="--", linewidth=1)
    ax.text(datetime.fromisoformat("2026-10-01"), PASSIVE_LIMIT * 1.12,
            "5-minute requirement (NFR-01)", fontsize=8, color="#555")
    ax.axvline(cut, color="#555", linestyle=":", linewidth=1)
    ax.text(cut, max(r["wall"] for r in runs) / 1.6, f"  optimised {cut:%d %b}",
            fontsize=8, color="#555")
    ax.set_yscale("log")
    ax.set_yticks([60, 300, 1800, 7200, 43200], ["1 min", "5 min", "30 min", "2 h", "12 h"])
    ax.yaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d %b"))
    ax.set_ylabel("run time (log scale)")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def figure_accuracy(path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [s for s in DEV_SAMPLES if s[2] and s[3] and s[4]]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    for y, (*_, before, after, _note) in enumerate(rows):
        for (k, n), colour, marker, label in ((before, "#c2410c", "o", "baseline"),
                                              (after, "#1d4ed8", "s", "Newseye")):
            low, high = wilson(k, n)
            ax.errorbar(k / n, y, xerr=[[k / n - low], [high - k / n]], fmt=marker,
                        color=colour, capsize=3, label=label if y == 0 else None)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{r[1]}\n(baseline: {r[2]})" for r in rows], fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(len(rows) - 0.5, -0.5)
    ax.set_xlabel("share correct, with 95% Wilson interval")
    ax.legend(fontsize=8, loc="lower left")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def figure_coherence(rows, floor, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    values = [r["coherence"] for r in rows]
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.hist(values, bins=30, color="#1d4ed8", alpha=0.8)
    ax.axvline(floor, color="#c2410c", linestyle="--")
    below = sum(1 for v in values if v < floor)
    ax.text(floor, ax.get_ylim()[1] * 0.9, f"  floor {floor}: {below} of {len(values)} "
            f"below get no page", fontsize=8, color="#c2410c")
    ax.set_xlabel("cluster coherence (mean pairwise cosine similarity)")
    ax.set_ylabel("stories")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def pct(k, n):
    low, high = wilson(k, n)
    return f"{k}/{n} = {k / n:.0%} ({low:.0%}-{high:.0%})"


def main():
    from backend.config import CLUSTER_MIN_COHERENCE, RSS_FEEDS

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(FIGURES, exist_ok=True)
    runs = parse_runs()
    cut = datetime.fromisoformat(OPTIMISED)
    before = [r for r in runs if r["when"] < cut]
    after = [r for r in runs if r["when"] >= cut]
    clusters = coherences()

    figure_runtime(runs, os.path.join(FIGURES, "fig-passive-runtime.png"))
    figure_accuracy(os.path.join(FIGURES, "fig-dev-accuracy.png"))
    figure_coherence(clusters, CLUSTER_MIN_COHERENCE,
                     os.path.join(FIGURES, "fig-coherence.png"))

    lines = [f"# Evaluation evidence - {datetime.now():%Y-%m-%d %H:%M}", "",
             "Regenerate with `python -m backend.scripts.evaluation`. Intervals are 95% "
             "Wilson score intervals for proportions and a Fisher z interval for the rank "
             "correlation.", "",
             "## Development hand-checks", "",
             "Each sample was drawn and marked by hand while the component was being built, "
             "so each measures the system on data that shaped it. They show the effect of "
             "each change against its baseline; they are not held-out results.", "",
             "| Task | Measure | Baseline | Before | Newseye | Note |",
             "|---|---|---|---|---|---|"]
    for task, measure, base_name, before_kn, after_kn, note in DEV_SAMPLES:
        lines.append(f"| {task} | {measure} | {base_name or '-'} | "
                     f"{pct(*before_kn) if before_kn else '-'} | "
                     f"{pct(*after_kn) if after_kn else '-'} | {note} |")
    low, high = fisher_interval(ORDERING["rho"], ORDERING["n"])
    lines += ["", f"Story ordering: number of outlets against checkable differences, "
                  f"Spearman ρ = +{ORDERING['rho']:.2f} (95% CI {low:+.2f} to {high:+.2f}, "
                  f"p = {ORDERING['p']}, n = {ORDERING['n']} stories).", "",
              "![Development accuracy against baselines](../figures/fig-dev-accuracy.png)", "",
              "*Figure: development hand-checks, baseline against Newseye, with 95% "
              "intervals. The name result is in-sample.*", ""]

    lines += ["## Performance over repeated runs (NFR-01)", "",
              f"Every scheduled passive run logged between {runs[0]['when']:%d %b} and "
              f"{runs[-1]['when']:%d %b %Y}, on the development laptop (NVIDIA T500, 4 GB), "
              f"with the live feeds as workload. Wall-clock time per run.", "",
              "| Period | Runs | Median | Middle half | 95th percentile | Slowest | "
              f"Within {PASSIVE_LIMIT // 60} minutes |", "|---|---|---|---|---|---|---|"]
    # Wall-clock time counts the laptop asleep mid-run; runs from the optimisation
    # also log the time spent working, which is what the requirement is about.
    working = [r for r in after if r["work"] is not None]
    for label, values in ((f"before {OPTIMISED}, wall clock", [r["wall"] for r in before]),
                          (f"from {OPTIMISED}, wall clock", [r["wall"] for r in after]),
                          (f"from {OPTIMISED}, working time", [r["work"] for r in working])):
        if not values:
            continue
        d = describe(values)
        lines.append(f"| {label} | {d['n']} | {d['median']:.0f} s | {d['q1']:.0f}-{d['q3']:.0f} s"
                     f" | {d['p95']:.0f} s | {d['max']:.0f} s | {d['within']}/{d['n']} "
                     f"({d['within'] / d['n']:.0%}) |")
    stage_times = defaultdict(list)
    for run in after:
        for name, seconds in run["stages"].items():
            stage_times[name].append(seconds)
    if stage_times:
        lines += ["", "Median stage times from " + OPTIMISED + ": " + ", ".join(
            f"{name} {statistics.median(v):.1f} s (n={len(v)})"
            for name, v in stage_times.items()) + "."]
    slow = [r for r in after if r["wall"] > PASSIVE_LIMIT and r["stages"]]
    if slow:
        # which stage ate the time: computation, or waiting on disk and network
        dominant = Counter(max(r["stages"], key=r["stages"].get) for r in slow)
        lines += ["", f"Runs over {PASSIVE_LIMIT // 60} minutes from {OPTIMISED}: "
                      f"{len(slow)}, each dominated by "
                  + ", ".join(f"{stage} ({count})" for stage, count in dominant.most_common())
                  + f". Clustering and summarising stayed under "
                    f"{max(r['stages'].get('cluster', 0) + r['stages'].get('summaries', 0) for r in slow):.0f} s "
                    "in every one of them: the overruns are waiting on disk (importing torch, "
                    "or the laptop asleep mid-import) and on the outlets' servers, not computation."]
    lines += ["", "![Passive run time per run](../figures/fig-passive-runtime.png)", "",
              "*Figure: wall-clock time of every scheduled passive run. Runs before the "
              f"{OPTIMISED} optimisation include Task Scheduler's I/O throttling and the "
              "laptop sleeping mid-run.*", ""]

    offline = [r for r in runs if len(r["feeds_failed"]) >= len(RSS_FEEDS) - 2]
    polled = [r for r in runs if r not in offline]
    failures = Counter()
    for run in polled:
        for outlet, _ in run["feeds_failed"]:
            failures[outlet.strip()] += 1
    run_level = [f for r in runs for f in r["run_failures"]
                 if not f.startswith("clustering rejected")]
    lines += ["## Reliability (NFR-02)", "",
              f"- {len(runs)} scheduled runs: {len(runs) - sum(1 for r in runs if r['run_failures'])} "
              f"completed every stage; {len(run_level)} stage failure(s): "
              + ("; ".join(sorted({re.sub(r"\s*\(.*|\[WinError \d+\]\s*", "", f)
                                   for f in run_level})) or "none") + ".",
              f"- {len(offline)} runs found nearly every feed unreachable at once: the laptop "
              f"was offline. Each was logged and exited cleanly.",
              f"- Of the other {len(polled)} runs, the feeds that failed at least once:", "",
              "| Outlet | Runs failed | Available |", "|---|---|---|"]
    for outlet, count in failures.most_common():
        lines.append(f"| {outlet} | {count} | {1 - count / len(polled):.0%} |")

    values = [r["coherence"] for r in clusters]
    below = sum(1 for v in values if v < CLUSTER_MIN_COHERENCE)
    lines += ["", "## Cluster coherence", "",
              f"{len(values)} stories in the current window: median coherence "
              f"{statistics.median(values):.2f}; {below} ({below / len(values):.0%}) below the "
              f"{CLUSTER_MIN_COHERENCE} floor, which get no story page.", "",
              "![Cluster coherence](../figures/fig-coherence.png)", "",
              "*Figure: coherence of every story in the current 7-day window, with the "
              "floor below which a cluster is treated as a grab-bag.*"]
    out = os.path.join(OUT, f"evaluation-{datetime.now():%Y-%m-%d}.md")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
