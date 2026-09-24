# Newseye
A media-literacy tool for Kenyan news. It groups articles from 12 Kenyan outlets
that are reporting the same event, then shows a reader what each outlet included,
what it left out, how it described the people involved, and which numbers it
published — with the sentence around every number and a link to the original.

It issues no verdicts. There is no accuracy score, no trust ranking, no
"contradiction detected" badge. The comparison is presented and the reader draws
the conclusion, because that is the only division of labour that survived
measurement on this corpus.

## What it found, and what that changed

The project began as contradiction detection. That did not work, and the
negative results shaped everything that followed:

- **Contradiction detection found nothing.** Across 151 story groups, zero
  genuine contradictions between two different outlets. Kenyan outlets rarely
  negate each other — they *omit* differently. Omission became the product.
- **Figure-conflict adjudication produced no true positive** at either 800 or
  2,162 articles. Every firing was a scope mismatch: a ward prize weighed
  against a county prize, "six treated at the scene" against the "eight injured"
  that included them. Deciding was removed; the figure *digest* replaced it,
  surfacing numbers with their context and declining to rule.
- **Stance classification was unreliable.** It labelled a story headlined
  "Appoints Kenyan Diplomat to Crucial New Role" as critical with 0.796
  confidence, and the same DeBERTa checkpoint later marked a sentence as
  contradicting an identical copy of itself at 0.853. Removed.
- **Abstractive summarisation misspelled Kenyan names** in 77 of 149 summaries
  ("Ruti" for Ruto, "Karuta" for Karua). Replaced with extractive selection: the
  member headline closest to the cluster centroid. Nothing is generated, so
  nothing can be invented.
- **Cross-source yield is accelerating, not saturating.** Subsampling the corpus
  and re-clustering fits an exponent of 1.32 on three-outlet stories, so a
  doubling of the corpus implies roughly 2.5× as many comparable stories.

## Architecture

Two tiers, because the costs are wildly different.

**Passive tier** — unattended, one ordered command. Polls RSS, embeds and
classifies, and re-clusters when the corpus has moved enough to be worth it.
Runs in ~80–170s on a 1,500-article window.

```
Task Scheduler → pythonw.exe -m backend.passive --log logs\passive.log
   ingest    feedparser → SHA-256 dedupe → MiniLM embedding → zero-shot topic
   cluster   HDBSCAN over a 7-day window → coherence → degeneracy guard
   summarise one extractive headline per cluster
```

Clustering rebuilds `clusters` and `cluster_members` with
`TRUNCATE ... RESTART IDENTITY CASCADE`, which also clears `cluster_analysis` —
so the summarise stage is mandatory, not optional.

**Active tier** — on-demand per cluster, ~7–20s. Fetches article text
transiently, derives claims, coverage, figures and framing, stores only the
derived results, and discards the text.

```
python -m backend.active --min-sources 3
   claims    spaCy sentence extraction around quantities
   coverage  group claims by meaning, then set arithmetic: who carried each fact
   figures   read every number, label it, show it with its source and context
   framing   sentiment scoped to sentences naming one entity, per outlet
```

`backend/analysis/` holds the analysis modules, `backend/nlp/` the embedding,
clustering and search, `backend/ingestion/` the feed reading, `backend/db/` the
schema and connection.

## Models

Four models, each doing one job. Every one is named explicitly in
`backend/config.py`, so none of them is ever a library default.

| Model | Size | Used in | Role |
|---|---|---|---|
| `all-MiniLM-L6-v2` (sentence-transformers) | 92 MB | `nlp/embeddings.py` | Embeds every article for clustering and search; groups claims into facts for the coverage table; picks each story's representative headline; orders figures within a group |
| `deberta-v3-base-zeroshot-v1.1-all-33` | 380 MB | `nlp/classification.py` | Gives each article a topic label at ingest |
| `twitter-roberta-base-sentiment-latest` | 1 GB | `analysis/framing.py` | Scores the sentences that name a person or institution, averaged per outlet |
| spaCy `en_core_web_sm` | 15 MB | `analysis/claims.py` | Splits articles into sentences and tags names, places and quantities; also used to name each story's subject |

HDBSCAN does the clustering, but it is an algorithm rather than a trained model.

No model decides what is true, which outlet is right, or whether two figures
agree. They group, label and order things; the reader interprets them.

## Setup

Requires **PostgreSQL with the pgvector extension** (developed on 0.8.2) and
Python 3.13.

```bash
python -m venv .venv
.venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python install_spacy_model.py   # fetches en_core_web_sm
```

Create an empty database named `articles`, then point the password at it — the
password is never stored in the repo (see `.env.example`):

```sql
CREATE DATABASE articles;
```

```bash
export DB_PASSWORD=...           # Windows: $env:DB_PASSWORD = "..."
python -m backend.db.migrations
```

That one command creates the pgvector extension, all four tables and every
index, and is safe to re-run. Nothing else is needed to get a working schema.

Connection settings other than the password are in `backend/db/connection.py`;
feeds, thresholds and model names are in `backend/config.py`.

The ~1.5GB of models are downloaded from HuggingFace on first use and cached in
`~/.cache/huggingface` — outside the repository and outside any synced folder.
No cloud storage is involved.

## Running

```bash
python -m backend.passive                 # ingest, then cluster if due
python -m backend.passive --cluster       # force the clustering stage
python -m backend.active --min-sources 3  # pre-compute the deep analysis
python -m backend.nlp.search "police shot protesters"
```

To schedule the passive tier on Windows every two hours:

```powershell
powershell -ExecutionPolicy Bypass -File backend\scripts\schedule_ingestion.ps1
```

It registers `pythonw.exe` directly (no console window appears) at normal
priority — Task Scheduler's default priority 7 applies background I/O
throttling, which stretched a 139-second run past eleven minutes.

## The demo site

```bash
python -m backend.scripts.export_review --top 14
python -m backend.scripts.build_site
# open site/index.html
```

A static dashboard plus one page per story. **Cluster IDs are reassigned on
every clustering run**, so `story-N.html` links go stale once the passive tier
next runs; regenerate both commands together. Stable story IDs are the main
outstanding piece of work.

## Tests

```bash
pip install -r requirements-dev.txt
ruff check backend                          # 0 findings
python -m backend.scripts.test_casualties   # 15/15
python -m backend.scripts.test_figures      # 14/14 + 1 documented limitation
```

All four run on every push via `.github/workflows/ci.yml`, along with a job that
builds the schema from an empty pgvector database and asserts the result.

Both assert on the shipping figure digest. They were rewritten after the
adjudicator was removed, and immediately caught a real bug: the digest was
grouping a death toll with an injury count and presenting them as rival counts
of one number.

Other scripts under `backend/scripts/` are experiments whose results are quoted
above — `density_curve.py` (yield scaling), `benchmark_separation.py` and
`tune_clustering.py` (clustering parameters), plus inspection helpers.

## Known limitations

- **Access is the binding constraint.** Around 30% of articles in a story cannot
  be read — paywalls and 403s. Those outlets are shown as "could not read" and
  are never counted as having omitted anything, because a paywall is not an
  editorial choice.
- **Cluster precision bounds every feature.** The coverage arithmetic is exact,
  but it is only meaningful when the cluster really is one story. Coherence
  measures topical tightness, not event identity, so blackout notices and an
  earnings report for the same utility can score 0.685 and still be a grab-bag.
- **Model loading dominates runtime** — about 71% of a passive run is spent
  importing torch to do ~36s of work. A long-lived worker would fix it.

## Onedrive move
- Project was initially on Onedrive which increased the load times of the project overall so
  benchmark numbers shall be updated accordingly.

Final-year project, Strathmore University.
