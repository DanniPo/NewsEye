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
  confidence. Removed. The same DeBERTa checkpoint was also recorded marking a
  sentence as contradicting an identical copy of itself at 0.853 - but that
  checkpoint has two labels with *entailment* first, and 0.853 is what an
  identical pair's entailment score looks like read in a three-label model's
  order (contradiction first). Read by its own config, it scores identical
  pairs 0.99 entailment both ways; see the next point.
- **Similarity alone merged different facts in the coverage table.** Of 30
  hand-checked cross-outlet pairs it had grouped, 17 were different facts: the
  Health CS saying the Ebola patient was a Kenyan citizen, filed as the same
  fact as the CS describing the patient's route. Each match is now also put to
  NLI read both ways. An outlet whose sentence is close but not the same is
  shown as *said something related*, with its sentence, and is neither
  credited nor counted as omitting. On the sample: wrong merges 17 to 1, false
  omissions none.
- **Abstractive summarisation misspelled Kenyan names** in 77 of 149 summaries
  ("Ruti" for Ruto, "Karuta" for Karua). Replaced with extractive selection: the
  member headline closest to the cluster centroid. Nothing is generated, so
  nothing can be invented.
- **Cross-source yield is accelerating, not saturating.** Subsampling the corpus
  and re-clustering fits an exponent of 1.32 on three-outlet stories, so a
  doubling of the corpus implies roughly 2.5× as many comparable stories.
- **The number of outlets is what predicts a story worth comparing.** On 63
  analysed stories, the outlets covering a story tracked how many checkable
  differences their coverage showed (Spearman ρ +0.40, p 0.001). People named
  (ρ −0.16), institutions named and conflict verbs in headlines ("slams",
  "accuses") added nothing to the ordering; at 12 stories people named had
  looked promising (+0.42) and was noise. A dispute between politicians is not
  the same as outlets reporting it differently. Stories are analysed most
  outlets first, as before.

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

Clustering re-runs HDBSCAN over the whole window, then matches each new cluster
to the stored one it continues (sharing at least half the smaller membership).
A continued story keeps its id; one with identical members also keeps its
summary and deep analysis. One whose members changed has its analysis cleared,
new stories get fresh ids, and ids are never reused. The summarise stage fills
in what was cleared, so it is still mandatory, not optional.

**Active tier** — on-demand per cluster, ~7–20s. Fetches article text
transiently, derives claims, coverage, figures and framing, stores only the
derived results, and discards the text.

```
python -m backend.active --min-sources 3
   claims    spaCy sentence extraction around quantities
   coverage  group claims by meaning, check each match with NLI, then set
             arithmetic: who carried each fact, who said something related
   quotes    who was quoted saying what; each outlet's version of a remark
             side by side: same words, shorter, longer, or worded differently
   figures   read every number, label it, show it with its source and context
   framing   sentiment scoped to sentences naming one entity, per outlet
```

Quote speakers are found from the reporting verb ("Ethekon said"), a pronoun
or bare title ("he said", "the DP said") resolved to the nearest person who
spoke or acted, or the last speaker when a quote paragraph runs on without
attribution. On three successive hand-checked samples of 30 quotes the speaker
was right for 24 of 30, then 19 of 21 attributed, then 25-26 of 26 attributed;
a quote the rules cannot place is shown as unattributed rather than guessed.

`backend/analysis/` holds the analysis modules, `backend/nlp/` the embedding,
clustering and search, `backend/ingestion/` the feed reading, `backend/db/` the
schema and connection.

## Models

Four models, each doing one job. Every one is named explicitly in
`backend/config.py`, so none of them is ever a library default.

| Model | Size | Used in | Role |
|---|---|---|---|
| `all-MiniLM-L6-v2` (sentence-transformers) | 92 MB | `nlp/embeddings.py` | Embeds every article for clustering and search; groups claims into facts for the coverage table; picks each story's representative headline; orders figures within a group |
| `deberta-v3-base-zeroshot-v1.1-all-33` | 380 MB | `nlp/classification.py`, `nlp/nli.py` | Gives each article a topic label at ingest; in the active tier, checks whether two sentences or two quotes say the same thing (NLI, both directions) |
| `twitter-roberta-base-sentiment-latest` | 1 GB | `analysis/framing.py` | Scores the sentences that name a person or institution, averaged per outlet |
| spaCy `en_core_web_sm` | 15 MB | `nlp/entities.py` | Splits articles into sentences and tags names, places and quantities; also used to name each story's subject and to read who does what in a headline |

HDBSCAN does the clustering, but it is an algorithm rather than a trained model.

### Kenyan names

spaCy's small model was trained on American news, and on this corpus it tagged
Kenyan names and institutions correctly in 26% of headlines and 74% of snippet
sentences: "Ruto" missed in 38 of 40 headlines, "Kindiki" called an organisation
in 36 of 40. Two additions in `nlp/entities.py` correct it after it runs:

- **A list**, `backend/data/kenya_entities.json`: 107 people, institutions, the
  47 counties and main towns, each person with an id so "Riggy G", "Gachagua"
  and "Rigathi Gachagua" are one person. Ambiguous names are tagged but never
  resolved: "Odinga" is Raila, Winnie or Oburu, and "Lusaka" is left out
  because it is also Zambia's capital. Listed names: 26% → 98% in headlines.
- **A title rule** for names nobody listed: the capitalised words after "CS",
  "MP", "Governor", "Senator" and similar. Unlisted names after a title:
  82% → 93%.

Headlines in Title Case are put back into sentence case first
(`nlp/truecase.py`), using how each word is written in the snippets.

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
python -m backend.nlp.search "police shot protesters"   # related stories grouped
python -m backend.scripts.visualize_clusters --topic Politics
python -m backend.analysis.portrayal Gachagua       # how each outlet presents him
```

`portrayal` sets outlets side by side for one public figure: how many of each
outlet's articles name them, whether they appear speaking, acting, acted on, or
inside someone else's quote, the verbs used ("claims", "assures", "slams"), the
titles given, and the headlines themselves. Outlets that never name the person
are listed too: across the corpus, none of KBC's 318 articles or Kenya News'
208 names Rigathi Gachagua, while both cover Kithure Kindiki. It issues no bias
score; the comparison and the headlines are the evidence, and the reader judges.
On a hand-checked random sample of 40 headline mentions it assigned the right
role to 34.

To schedule the passive tier on Windows every two hours:

```powershell
powershell -ExecutionPolicy Bypass -File backend\scripts\schedule_ingestion.ps1
```

It registers `pythonw.exe` directly (no console window appears) at normal
priority — Task Scheduler's default priority 7 applies background I/O
throttling, which stretched a 139-second run past eleven minutes.

A static dashboard plus one page per story. A story keeps its cluster id across
clustering runs for as long as it stays in the window, so `story-N.html` links
survive a re-cluster; a link goes dead only when its story ends. On one run
against live data, 342 of 348 clusters carried over and 307 kept their
summaries untouched.

The site also has a People section: a page for every listed person named in
at least 6 articles by 2+ outlets, built from the same portrayal analysis -
who names them (outlets that never do included), how they appear in each
outlet, and each outlet's verbs, titles and headlines. Story pages link to the
people they name. It needs the database and spaCy at build time; without them
the rest of the site builds as before. Each outlet's row also gives a headline
tone - an automatic reading of the headlines and opening lines as a whole,
labelled as a hint that can be wrong ("Ruto condemns the killings" reads
negative without being negative about Ruto) - and links to its headlines so
the reader can open the articles themselves.

The dashboard's *Where outlets differ most* lists the analysed stories with the
most differences a reader can check on the page - related wording, different
figures, quotes shortened or reworded, a wide tone gap - each with its reasons.
"Facts not carried by all" is not counted: it was 100% in half the stories.

Story pages are built only for clusters at or above the 0.50 coherence floor.
The export once skipped that check, and 3 of 13 demo pages were loose clusters
- the Strait of Hormuz grouped with Kenya's UAE exports - whose coverage tables
reported omissions that never happened, because the outlets were not covering
the same event. Figures are shown in bold inside their own context.

## Tests

```bash
pip install -r requirements-dev.txt
ruff check backend                          # 0 findings
python -m backend.scripts.test_casualties   # 15/15
python -m backend.scripts.test_figures      # 14/14 + 1 documented limitation
python -m backend.scripts.test_cluster_ids  # 10/10
python -m backend.scripts.test_entities     # 21/21
python -m backend.scripts.test_portrayal    # 18/18
python -m backend.scripts.test_coverage     # 6/6
python -m backend.scripts.test_quotes       # 21/21
python -m backend.scripts.test_divergence   # 6/6
```

All of these run on every push via `.github/workflows/ci.yml`, along with a job that
builds the schema from an empty pgvector database and asserts the result.

The two figure tests assert on the shipping figure digest. They were rewritten after the
adjudicator was removed, and immediately caught a real bug: the digest was
grouping a death toll with an injury count and presenting them as rival counts
of one number.

Other scripts under `backend/scripts/` are experiments whose results are quoted
above — `density_curve.py` (yield scaling), `benchmark_separation.py` and
`tune_clustering.py` (clustering parameters), plus inspection helpers.

For a demonstration, `pick_showcase.py` chooses contested stories that between
them show every feature of a story page - related wording, differing figures,
a remark quoted by several outlets, reworded quotes, framing, people with
pages - instead of the usual most-outlets-first order:

```bash
python -m backend.scripts.pick_showcase --analyse 25 --n 14
python -m backend.scripts.export_review <ids it prints> --note showcase
python -m backend.scripts.build_site
```

`--note showcase` makes the dashboard say the stories were chosen this way, so
a curated set is never mistaken for a typical day.

To send the site to someone, fold it into one HTML file (about 5.5 MB with
the search index):

```bash
python -m backend.scripts.single_file --site site --out dist/newseye.html
```

Every page becomes a section of that file and links between pages keep
working, so it opens from an email attachment or a phone's downloads with no
server. It needs a connection only for fonts, the original articles, and the
meaning-based search model (search falls back to matching words without it).

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
