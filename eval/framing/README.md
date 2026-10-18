# Framing evaluation: sentence tone against targeted sentiment

Newseye describes how each outlet presents a person by scoring the sentences
that name them. Until now it scored the whole sentence's tone. So "Ruto
condemns the killings in Kisumu" read as negative, although nothing in it is
negative about Ruto. Targeted sentiment instead scores the writer's attitude
toward the marked person. It uses GRU-TSC, the NewsMTSC model from Hamborg and
Donnay (2021), available as the `NewsSentiment` package.

This folder holds two evaluations:

1. **The NewsMTSC benchmark** (`benchmark.md`). Both methods are scored on the
   paper's human-labelled test sets. This has been run, and it decided the
   switch (step 0).
2. **Newseye's own corpus** (steps 2 to 6). A labelled sample of Kenyan
   headlines, opening lines and article sentences. It confirms, or overturns,
   the benchmark on the text Newseye actually reads.

## 0. The benchmark (done)

```bash
python -m backend.eval.benchmark_framing
```

This downloads the dev and test splits of NewsMTSC's two test sets into
`newsmtsc/`, which is not committed, so cite the paper.

- **rw:** the real-world distribution of sentiment in news.
- **mt:** every sentence names at least two people.

Each method's neutral band is tuned on dev, and both are judged on test. The
decision rule was fixed before the first run and is stated at the top of
`benchmark.md`. The same file has a behaviour check on constructed Kenyan
sentences.

**Result (16 Oct 2026).** Targeted beat sentence tone by +0.150 F1m on rw (95%
CI +0.113 to +0.189) and +0.199 on mt (+0.167 to +0.232), so the rule was met.
People are now scored targeted, at the ±0.29 threshold tuned on rw dev.
Neither combination beat the single model on both sets. The blend put all its
weight on targeted; the stacked model gained +0.021 on rw but only +0.004 on
mt, where its interval includes zero.

The benchmark is in-domain for GRU-TSC, which was trained on NewsMTSC, and it
is US political news. That makes it the right test of which existing tool to
use, but not a test on Kenyan text. Steps 2 to 6 provide that.

## 1. Set up the targeted model (once)

NewsSentiment 1.2.28 needs Python 3.8 to 3.11, torch ≥ 1.12 and < 2.1, and
transformers 4.17 to 4.24. Newseye runs Python 3.13, so the model gets its own
environment. Newseye's environment is left alone.

On Windows, without installing a system Python, use `uv` to fetch a standalone
Python 3.11 for your user account:

```powershell
py -3.13 -m pip install --user uv
uv python install 3.11
uv venv --seed --python 3.11 $env:USERPROFILE\.venvs\newsmtsc
uv pip install --python $env:USERPROFILE\.venvs\newsmtsc\Scripts\python.exe NewsSentiment==1.2.28 "numpy<2"
```

`numpy<2` matters: torch 2.0 was built against numpy 1 and fails under numpy 2.

Then download the model weights (584 MB) once:

```powershell
& $env:USERPROFILE\.venvs\newsmtsc\Scripts\python.exe -m NewsSentiment download
```

If that is slow or keeps dropping, the file can be fetched with any download
tool that can resume:

```bash
curl -L -C - -o ~/.cache/torch/hub/pretrained_models/state_dicts/grutsc_v1-0-0 \
  https://github.com/fhamborg/NewsMTSC/releases/download/v1.0.0/grutsc
```

The worker will not start without the weights. It reports where they are
missing, so the download never happens unannounced inside a site build.

**Use the GPU.** PyPI's Windows build of torch 2.0.1 is CPU-only. With an
NVIDIA GPU, replace it with the CUDA 11.8 build of the same version (2.6 GB):

```powershell
uv pip install --python $env:USERPROFILE\.venvs\newsmtsc\Scripts\python.exe `
  --index-url https://download.pytorch.org/whl/cu118 --reinstall-package torch torch==2.0.1+cu118
```

NewsSentiment uses the GPU automatically when torch can see it. On the
development laptop (NVIDIA T500, 4 GB), real news sentences took 1.3 to 2.4 s
a mention on the CPU and 0.26 s on the GPU, using 1.6 GB of GPU memory. Batch
size made no difference: most of the remaining time goes on NewsSentiment's own
text preparation, which runs in Python. Scores are cached (`TARGETED_CACHE`), so
each mention is scored only once.

On Linux or macOS, with Python 3.11:

```bash
python3.11 -m venv ~/.venvs/newsmtsc
~/.venvs/newsmtsc/bin/pip install NewsSentiment==1.2.28 "numpy<2"
```

`backend/config.py` looks for the interpreter at `~/.venvs/newsmtsc`, or at
`NEWSMTSC_PYTHON` if that is set. On first use,
`backend/analysis/targeted.py` starts `backend/analysis/tsc_worker.py` in that
environment and keeps it running for the life of the process. The first start
also fetches `roberta-base` (about 500 MB) into the Hugging Face cache. Worker
output goes to `logs/tsc_worker.log`.

Check that it works:

```bash
python -c "from backend.analysis.targeted import targeted_sentiment as t; print(t([('Ruto condemns the killings in Kisumu.', 0, 4)]))"
```

A sentence-level model calls that sentence negative. The targeted score toward
Ruto should be near zero or positive.

If the environment is missing or the worker fails, nothing breaks. Every
mention is then scored by sentence tone, as before.

## 2. Draw the sample

```bash
python -m backend.eval.sample_framing --dump-claims eval/framing/claims.jsonl   # body sentences
python -m backend.eval.sample_framing --n 300 --out eval/framing --claims eval/framing/claims.jsonl
```

This writes three files:

- **`sample.csv`:** the metadata. Keep it from the annotators.
- **`sheet_A.csv` and `sheet_B.csv`:** one sheet per annotator.

How the sample is drawn:

- Each outlet's headlines, opening lines and body sentences take turns, so every
  outlet and every field is represented.
- 60% of items (`--person-share`) come from texts that name a person, with the
  person taken first. Targeted scoring applies to people, so they need the most
  items. The rest come from any text, so other types can be judged too.
- An article gives one text, and a text gives at most two items, so a sentence
  naming two people is judged for each.
- Outlet names are hidden from the sheets.
- The first 30 items are the calibration set (step 3). Discussed labels are not
  independent, so these items go to the dev split, which is used only for
  tuning. They are joined by enough other items to make 30% of the sample.

300 items is a workable minimum. After excluding bad items and holding 30% for
tuning, about 200 remain for the test. That is enough to show a large
difference between the methods. A gap of a point or two will sit inside the
bootstrap interval and needs more items.

Before labelling, `python -m backend.eval.score_framing predict` followed by
`compare` shows how often the two methods disagree on this sample. That shows
what switching changes, not which method is right. Don't show it to the
annotators.

## 3. Label: two people, separately

Each annotator fills the `label` column of their own sheet without talking to
the other. Use the guide below, and write anything uncertain in `notes`.

### Annotation guide

These instructions follow the method in Hamborg and Donnay (2021), Section
3.3. It found two things that raise agreement on news text: judging from the
*writer's* point of view rather than your own, and attending to *how* things
are described as well as *what* happened.

> Imagine you are the journalist who wrote this text. Writers can make a
> person look better or worse through what they report the person doing,
> through the words they choose ("reforms" or "hikes", "critics" or
> "rivals", "claims" or "explains"), and through whose words they quote.
>
> What is **the writer's attitude toward the entity in [[double brackets]]**?
> Judge only that entity. A sad or violent event is not negative toward
> someone just because they appear in it. If the same text appears again
> with a different entity marked, judge each one separately.
>
> Your own opinion of the person does not count. Two people with opposite
> politics should give the same label.

| label | meaning |
|---|---|
| -3 | strongly negative |
| -2 | negative |
| -1 | slightly negative |
| 0 | neutral, or can't tell |
| 1 | slightly positive |
| 2 | positive |
| 3 | strongly positive |
| x | the marked words are not a real entity (an NER error), or the text can't be judged |

Agree on these worked examples before starting. Write your own from the corpus
too, and add them here.

- `[[Ruto]] condemns the killings in Kisumu` → 0 or +1. The event is
  negative; the writer shows Ruto responding to it.
- `[[Gachagua]] claims he was sidelined` → about -1. "Claims" signals the
  writer's doubt; "says" would be 0.
- `Police tear-gas supporters of [[Kalonzo]]` → 0 for Kalonzo. Something is
  done to his supporters, but nothing is said about him.
- `[[Raila]] hits back at critics over IEBC stance` → 0. Conflict alone is
  not an attitude.

The 7-point scale is collapsed to negative, neutral and positive for scoring,
as NewsMTSC does. The finer scale makes annotators commit on slightly positive
and slightly negative cases instead of calling them neutral.

Calibrate first. Both annotators label the first 30 items, compare, and talk
through disagreements. Then each labels the rest alone.

## 4. Agreement and the gold labels

```bash
python -m backend.eval.score_framing agree --dir eval/framing
```

This prints Cohen's kappa and writes `gold.csv`:

- Items where both annotators chose the same class are filled in.
- For the rest, sit down together and fill `gold` with `negative`, `neutral`,
  `positive` or `x`. Running `agree` again keeps what you've settled.

Kappa is reported on the items labelled independently, without the 30
calibration items. A quadratic-weighted kappa on the 7-point scale is reported
too. Report the kappa. The paper reports agreement in the 0.7s for its own
annotation (check the exact figures there before citing them). Below about 0.6,
the guide needs work before the labels can be trusted, whether by people or as
a benchmark for models.

## 5. Score and compare

```bash
python -m backend.eval.score_framing predict --dir eval/framing   # skip if already run
python -m backend.eval.score_framing report  --dir eval/framing
```

`predict` runs both methods once and saves `preds.csv`. `report` writes
`report.md`, which contains:

- **Metrics:** F1m (macro F1 over the three classes), F1pn (positive and
  negative only) and accuracy. These are the metrics NewsMTSC reports.
- **Methods:** each method at ±0.15 and at a threshold tuned on the dev split,
  plus the targeted model's own most-likely class.
- **A paired bootstrap interval** for the difference. If it excludes zero, the
  improvement is unlikely to be chance at this sample size.
- **Subsets:** headlines, snippets and body; PERSON and other types; texts
  naming one entity or several; agreed against settled items.
- **Confusion matrices,** and `errors.csv` for the error analysis.

What to expect, from the paper:

- NewsMTSC discarded sentences under 50 characters, so **headlines are outside
  its training data**. The headlines row shows whether that matters.
- It labels people only, so **watch the "not PERSON" row** before adding ORG or
  other types to `TARGETED_ENT_TYPES`.
- Its errors cluster on texts naming several entities, where it confuses one
  target for another. Compare the "names several" row with the "names one"
  row.

## 6. Error analysis

Fill `cause` in `errors.csv` for at least 50 rows. Use the categories from the
paper's Section 6 so your results can be set beside theirs. The report keeps
causes already filled in.

- `weak`: very weak, indirect or partly subjective sentiment
- `both-valid`: the prediction is also defensible
- `target-confusion`: the sentiment belongs to a different entity in the text
- `context`: the text alone doesn't show the attitude
- `gold-wrong`: on reflection, the gold label is wrong
- `headline-grammar`: compressed headline phrasing (a Newseye category)
- `kenyan-context`: needs local knowledge, Sheng or Swahili (a Newseye category)
- `none`: no apparent reason

## 7. The switch

`backend/config.py` holds the setting:

```python
FRAMING_SENTIMENT = "targeted"     # set from benchmark.md; the Kenyan report confirms or reverts it
FRAMING_TARGETED_THRESHOLD = 0.29  # tuned on NewsMTSC rw dev; retune on the Kenyan dev split
TARGETED_ENT_TYPES = {"PERSON"}    # add types only where the "not PERSON" row supports it
```

`analyze_framing` then scores each mention of a person toward that person and
records `scored_by` for each outlet: "targeted", "sentence" or "mixed".
Anything it can't score toward the entity falls back to sentence tone, so
nothing breaks if the worker is down. That covers other entity types, claims
stored before spans existed, and the model being missing. The portrayal script's
headline-tone hint does the same, and the people pages say which method scored
them.

`FRAMING_SENTIMENT=sentence` in the environment switches back without editing
any code.
