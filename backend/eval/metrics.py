"""Scoring a three-class sentiment method against gold labels.

The metrics NewsMTSC reports, so results here can be set beside the paper's:

    F1m    macro F1 over negative, neutral and positive
    F1pn   macro F1 over negative and positive only (neutral still counts as a
           wrong answer for them, it just has no F1 of its own)
    acc    accuracy

A method gives each item a score in -1..1 (P(positive) - P(negative)); a
threshold t turns it into a class: above t positive, below -t negative,
otherwise neutral. Thresholds are tuned on a dev split and judged on test.
"""
import random

from sklearn.metrics import cohen_kappa_score, confusion_matrix, f1_score

CLASSES = ("negative", "neutral", "positive")


def label(score, threshold=0.15):
    if score is None:
        return None
    if score > threshold:
        return "positive"
    return "negative" if score < -threshold else "neutral"


def f1m(gold, predicted):
    return float(f1_score(gold, predicted, labels=list(CLASSES), average="macro",
                          zero_division=0))


def f1pn(gold, predicted):
    return float(f1_score(gold, predicted, labels=["negative", "positive"], average="macro",
                          zero_division=0))


def accuracy(gold, predicted):
    return sum(g == p for g, p in zip(gold, predicted, strict=True)) / len(gold) if gold else 0.0


def scores(gold, predicted):
    return {"f1m": f1m(gold, predicted), "f1pn": f1pn(gold, predicted),
            "acc": accuracy(gold, predicted), "n": len(gold)}


def confusion(gold, predicted):
    """Rows are gold, columns predicted, both in CLASSES order."""
    return confusion_matrix(gold, predicted, labels=list(CLASSES)).tolist()


def tune_threshold(gold, values, grid=None, prefer=0.15):
    """The neutral band that maximises F1m on these items; ties go to the
    threshold nearest prefer, so a flat optimum does not drift."""
    grid = grid or [round(i / 100, 2) for i in range(0, 81)]
    best = max(grid, key=lambda t: (round(f1m(gold, [label(v, t) for v in values]), 6),
                                    -abs(t - prefer)))
    return best


def paired_bootstrap(gold, predicted_a, predicted_b, metric=f1m, resamples=5000, seed=0):
    """Difference metric(b) - metric(a) on these items, with a 95% interval from
    resampling items with replacement (both methods judged on the same resample).

    Returns (difference, low, high, share of resamples where b was not better)."""
    rng = random.Random(seed)
    n = len(gold)
    observed = metric(gold, predicted_b) - metric(gold, predicted_a)
    differences = []
    for _ in range(resamples):
        picks = [rng.randrange(n) for _ in range(n)]
        g = [gold[i] for i in picks]
        differences.append(metric(g, [predicted_b[i] for i in picks])
                           - metric(g, [predicted_a[i] for i in picks]))
    differences.sort()
    low = differences[int(0.025 * resamples)]
    high = differences[int(0.975 * resamples) - 1]
    not_better = sum(1 for d in differences if d <= 0) / resamples
    return observed, low, high, not_better


def compare_methods(dev, test, combined=False):
    """({method name: predicted classes on test}, {method: tuned setting}).

    dev and test are rows with "gold", "sentence" (score), "targeted" (score or
    None) and "probabilities" ([neg, neu, pos] or None). An item the targeted
    model could not score falls back to sentence tone, as it does in production.
    Order matters to callers: sentence ±0.15, targeted ±0.15, sentence tuned,
    targeted tuned, targeted most likely class; with combined=True, then the
    weighted blend and the stacked model, both fitted on dev alone.
    """
    def values(rows, key):
        return [r[key] if r[key] is not None else r["sentence"] for r in rows]

    gold_dev = [r["gold"] for r in dev]
    tuned = {key: tune_threshold(gold_dev, values(dev, key)) for key in ("sentence", "targeted")}
    predicted = {
        "sentence ±0.15": [label(v) for v in values(test, "sentence")],
        "targeted ±0.15": [label(v) for v in values(test, "targeted")],
        f"sentence, tuned ±{tuned['sentence']:.2f}":
            [label(v, tuned["sentence"]) for v in values(test, "sentence")],
        f"targeted, tuned ±{tuned['targeted']:.2f}":
            [label(v, tuned["targeted"]) for v in values(test, "targeted")],
        "targeted, most likely class": [
            label(r["sentence"]) if r["probabilities"] is None
            else CLASSES[max(range(3), key=lambda i: r["probabilities"][i])] for r in test],
    }
    if combined:
        weight, threshold = tune_blend(gold_dev, values(dev, "targeted"), values(dev, "sentence"))
        tuned["blend"] = (weight, threshold)
        predicted[f"combined: blend {weight:.1f} targeted + {1 - weight:.1f} sentence, "
                  f"±{threshold:.2f}"] = [
            label(weight * t + (1 - weight) * s, threshold)
            for t, s in zip(values(test, "targeted"), values(test, "sentence"), strict=True)]
        model = fit_stack(dev)
        tuned["stack C"] = float(model.C_[0])
        predicted["combined: stacked logistic regression"] = list(model.predict(features(test)))
    return predicted, tuned


def tune_blend(gold, targeted, sentence):
    """(weight on targeted, threshold) that maximise F1m; ties go to the most weight on
    targeted, then the threshold nearest 0.15 - the simplest combination that does
    as well."""
    best = None
    for step in range(11):
        weight = step / 10
        blended = [weight * t + (1 - weight) * s for t, s in zip(targeted, sentence, strict=True)]
        threshold = tune_threshold(gold, blended)
        key = (round(f1m(gold, [label(v, threshold) for v in blended]), 6), weight,
               -abs(threshold - 0.15))
        if best is None or key > best[0]:
            best = (key, weight, threshold)
    return best[1], best[2]


def features(rows):
    """What the stacked model sees: the targeted model's three probabilities and the
    sentence score. Unscored items get neutral probabilities."""
    return [[*(r["probabilities"] or (0.0, 1.0, 0.0)), r["sentence"]] for r in rows]


def fit_stack(dev):
    """Multinomial logistic regression over both models' outputs, its regularisation
    chosen by 5-fold cross-validation inside dev."""
    from sklearn.linear_model import LogisticRegressionCV
    return LogisticRegressionCV(Cs=10, cv=5, max_iter=5000).fit(
        features(dev), [r["gold"] for r in dev])


def table(rows):
    """Markdown table lines from a header row and data rows."""
    lines = ["| " + " | ".join(str(c) for c in rows[0]) + " |", "|" + "---|" * len(rows[0])]
    return lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows[1:]]


def kappa(labels_a, labels_b, weights=None):
    """Cohen's kappa; weights="quadratic" for the 7-point scale."""
    if not labels_a:
        return None
    return float(cohen_kappa_score(labels_a, labels_b, weights=weights))
