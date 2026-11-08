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
  cross-outlet pairs it had grouped, checked by Claude, 17 were different facts: the
  Health CS saying the Ebola patient was a Kenyan citizen, filed as the same
  fact as the CS describing the patient's route. Each match is now also put to
  NLI read both ways. An outlet whose sentence is close but not the same is
  shown as *said something related*, with its sentence, and is neither
  credited nor counted as omitting. On the sample: wrong merges 17 to 1, false
  omissions none. Of the pairs still grouped, 9 of 10 are one fact, and 4 of the 13
  real matches became "related". `backend/scripts/fact_pairs.py` draws a fresh sample
  for a person to mark.
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
A median run takes 131 s on a window of about 2,100 articles.

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
   framing   each outlet's attitude toward each named person (NewsMTSC), and
             the tone of sentences naming institutions and places
```

Quote speakers are found from the reporting verb ("Ethekon said"), a pronoun
or bare title ("he said", "the DP said") resolved to the nearest person who
spoke or acted, or the last speaker when a quote paragraph runs on without
attribution. On three successive samples of 30 quotes, checked by Claude, the speaker
was right for 24 of 30, then 19 of 21 attributed, then 25-26 of 26 attributed;
a quote the rules cannot place is shown as unattributed rather than guessed.

`backend/analysis/` holds the analysis modules, `backend/nlp/` the embedding,
clustering and search, `backend/ingestion/` the feed reading, `backend/db/` the
schema and connection.

## Models

Five models, each doing one job. Every one is named explicitly in
`backend/config.py`, so none of them is ever a library default.

| Model | Size | Used in | Role |
|---|---|---|---|
| `all-MiniLM-L6-v2` (sentence-transformers) | 92 MB | `nlp/embeddings.py` | Embeds every article for clustering and search; groups claims into facts for the coverage table; picks each story's representative headline; orders figures within a group |
| `deberta-v3-base-zeroshot-v1.1-all-33` | 380 MB | `nlp/classification.py`, `nlp/nli.py` | Gives each article a topic label at ingest; in the active tier, checks whether two sentences or two quotes say the same thing (NLI, both directions) |
| GRU-TSC from NewsSentiment 1.2.28 (NewsMTSC) | 584 MB | `analysis/targeted.py`, `analysis/tsc_worker.py` | Scores the writer's attitude toward each named person, per outlet, on story pages and in the people pages' headline tone |
| `twitter-roberta-base-sentiment-latest` | 1 GB | `analysis/framing.py` | Tone of whole sentences: for institutions and places, and wherever the targeted model cannot score a mention |
| spaCy `en_core_web_sm` | 15 MB | `nlp/entities.py` | Splits articles into sentences and tags names, places and quantities; also used to name each story's subject and to read who does what in a headline |

HDBSCAN does the clustering, but it is an algorithm rather than a trained model.

### How people are framed

Sentence tone reads "Ruto condemns the killings in Kisumu" as negative (−0.47)
although nothing in it is negative about Ruto. Targeted sentiment scores the
writer's attitude toward the marked person instead (+0.07, neutral). On
NewsMTSC's human-labelled test sets it beat sentence tone by +0.150 macro F1
(803 targets, 95% CI +0.113 to +0.189) and +0.199 (1,034 targets in sentences
naming two or more people, +0.167 to +0.232), passing a decision rule fixed
before the run; combining the two models added nothing beyond noise. See
`eval/framing/benchmark.md`.

NewsSentiment needs Python ≤ 3.11, torch < 2.1 and transformers ≤ 4.24, so it
runs as a worker in its own environment (`eval/framing/README.md` sets it up).
Scores are cached, so each mention is scored once (0.26 s each on the T500
GPU). Without the worker, everything falls back to sentence tone. The labelled
Kenyan sample in `eval/framing/` is the test that confirms the switch on Kenyan
text, or reverts it (`FRAMING_SENTIMENT=sentence`).

### Kenyan names

spaCy's small model was trained on American news, and on this corpus it tagged
Kenyan names and institutions correctly in 26% of headlines and 74% of snippet
sentences: "Ruto" missed in 38 of 40 headlines, "Kindiki" called an organisation
in 36 of 40. Two additions in `nlp/entities.py` correct it after it runs:

- **A list**, `backend/data/kenya_entities.json`: 107 people, institutions, the
  47 counties and main towns, each person with an id so "Riggy G", "Gachagua"
  and "Rigathi Gachagua" are one person. Ambiguous names are tagged but never
  resolved: "Odinga" is Raila, Winnie or Oburu, and "Lusaka" is left out
  because it is also Zambia's capital. Listed names: 26% → 98% of 522 headline
  mentions. That is in-sample: the list was built from the same corpus. The
  held-out evaluation in `docs/` measures it on headlines ingested later.
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
On a random sample of 40 headline mentions, checked by Claude, it assigned the right
role to 34.

To keep the live site current, run the whole pipeline every two hours: collect
and group (passive tier), compare every story without a comparison (active
tier), and rebuild the people pages once a day. Each stage runs as its own
process, a database lock stops two runs overlapping, and a failed stage stops
nothing after it:

```powershell
python -m backend.pipeline --log logs\pipeline.log     # one run, by hand
powershell -ExecutionPolicy Bypass -File backend\scripts\schedule_pipeline.ps1          # register, switched off
powershell -ExecutionPolicy Bypass -File backend\scripts\schedule_pipeline.ps1 -Enable  # register and switch on
Get-Content logs\pipeline.log -Wait -Tail 30          # watch a run
```

It registers `pythonw.exe` directly (no console window appears) at normal
priority — Task Scheduler's default priority 7 applies background I/O
throttling, which stretched a 139-second run past eleven minutes — and switches
off the older passive-only task (`schedule_ingestion.ps1`), which collected
without comparing. `DB_NAME` points every stage, and the API, at another
database, such as a copy to test on.

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

### Web API (in progress)

A read-only FastAPI layer over the stored results, for the React interface that
will replace the static site. It serves what the pipeline has stored and runs
no model per request except MiniLM for a search query.

```bash
python -m backend.db.migrations   # adds cluster_analysis.articles and the people table
python -m backend.people          # how each outlet presents each person (about 40 s)
uvicorn backend.api.main:app --reload   # http://127.0.0.1:8000/docs
python -m backend.scripts.test_api      # no database needed; --live adds the real one
```

| Endpoint | Returns |
|---|---|
| `GET /api/health` | Database counts and the time of the last run |
| `GET /api/stories?limit=&offset=&min_outlets=&sort=&topic=&source=` | Stories ordered by `outlets`, `differences` or `latest`, only one topic's or one outlet's (by its slug) when asked, with what a story card shows: checkable differences, facts not in every outlet, numbers to compare, unread outlets, and whether two outlets could be compared |
| `GET /api/contested?limit=&days=` | The latest stories whose coverage reports a dispute, most contested first, each with what was counted |
| `GET /api/topics` | How many multi-outlet stories each topic has |
| `GET /api/stories/{id}` | One story: articles, which outlets could be opened, coverage, quotes, figures laid out as the site shows them (groups, then figures with nothing to set beside), framing, and the listed people named in it |
| `GET /api/search?q=&limit=` | Articles closest in meaning, each with its story |
| `GET /api/people` | Everyone named often enough to compare: articles, outlets, title, tone mix and the outlets that never name them |
| `GET /api/people/{id}?records=` | One person's page, with each outlet's newest mentions and the verbs it reports their words with |
| `GET /api/sources` | Every outlet Newseye reads: articles and share, dates, stories shared with other outlets, how often its articles could be opened, leading topics. Counts, not ratings |
| `GET /api/sources/{slug}?stories=&recent=` | One outlet: its whole topic mix, newest headlines (each with its story) and newest stories |

Every database session is read-only (PostgreSQL refuses writes) with a 5-second
statement timeout; input is validated before it reaches the database; errors
return a status and a short message, never a traceback; CORS allows only
`NEWSEYE_API_ORIGINS` (default `http://localhost:5173`, the Vite dev server).
Each client may make 120 requests a minute, 30 of them searches
(`NEWSEYE_API_RATE`, `NEWSEYE_API_SEARCH_RATE`), and is answered 429 with
`Retry-After` beyond that. Responses carry a Content Security Policy that forbids
loading or framing anything.

For anything but local use, give the API its own database account, which can read
every table and write none. Choose a password and keep it out of the repository:

```powershell
$env:NEWSEYE_API_DB_PASSWORD = "..."
python -m backend.db.api_role
$env:NEWSEYE_API_DB_USER = "newseye_api"
uvicorn backend.api.main:app
```

Not yet done: logins and roles.
Which outlets could be opened is stored from 23 October 2026; a story analysed
before then reports it as not recorded until it is analysed again.

### React interface (in progress)

`frontend/` is the interface for the hosted version: the static site's pages,
White + Lime design and wording, reading the API above instead of an export.
Changes from the static site: a headline that names the outlets as the page
opens, a **Sources** page (every outlet, and a page for each) where the
dashboard's "snapshot" card was, a filter of the story list by outlet, more
stories on request, and transitions: pages slide and fade into one another,
a story's headline travels from its card to the story page, cards glide to their
new places when the list is re-ordered, and the tab highlight slides between a
story's sections. Every animation stops when the reader's system asks for
reduced motion, and the headline's opening run of names ends by itself within
five seconds.

```bash
uvicorn backend.api.main:app --port 8000     # the API, with DB_PASSWORD set
cd frontend
npm ci                                       # Node 22.12 or later
npm run dev                                  # http://localhost:5173, /api goes to the API
npm run typecheck && npm test                # 65 component and page tests, fake API
npm run e2e                                  # 8 end-to-end tests in Edge, real API and database
npm run build                                # dist/, static files for any web server
```

The tests that need no database also run in CI. Versions are pinned exactly, at
the newest release of the major versions the code was written against (React 19,
React Router 7, Vite 7, TypeScript 5.9, Vitest 4); `package.json` overrides keep
Vitest's optional peers from pulling in Vite 8. Hosted, the build should be
served with a Content Security Policy and the API behind the same origin, or
`VITE_API_BASE` pointing at it with that origin in `NEWSEYE_API_ORIGINS`.

## Tests

```bash
pip install -r requirements-dev.txt
ruff check backend                          # 0 findings
python -m backend.scripts.test_casualties   # 15/15
python -m backend.scripts.test_figures      # 15/15 + 1 documented limitation
python -m backend.scripts.test_cluster_ids  # 10/10
python -m backend.scripts.test_entities     # 22/22 (21 sentences + the list itself)
python -m backend.scripts.test_portrayal    # 23/23
python -m backend.scripts.test_coverage     # 6/6
python -m backend.scripts.test_quotes       # 21/21
python -m backend.scripts.test_divergence   # 7/7
python -m backend.scripts.test_robustness   # 18/18 boundary, exception, security, empty input
python -m backend.scripts.test_targeted     # 18/18 targeted tone: fallbacks, cache, eval maths
python -m backend.scripts.test_api          # 63/63 web API; --live adds 17 checks on the database
```

All of these run on every push via `.github/workflows/ci.yml`, along with a job that
builds the schema from an empty pgvector database and asserts the result, and one
that type-checks, tests and builds the React interface.

These commands keep a dated record in `docs/evidence/`:

```bash
python -m backend.scripts.test_record     # every suite: test ID, requirement, expected vs actual
python -m backend.scripts.end_to_end      # feeds -> database -> clusters -> analysis -> site,
                                          # checking each hand-off; site goes to dist/latest/
python -m backend.scripts.evaluation      # intervals, repeated-run performance, figures
python -m backend.scripts.heldout sample  # labelling sheets from data the code never saw
python -m backend.scripts.heldout score   # ...and their accuracy once labelled
```

`docs/testing-and-evaluation.md` brings these together: the test strategy, the
requirement traceability, the defect log (expected, actual, correction and
retest) and the evaluation. `docs/usability-test-plan.md` is the user test
protocol.

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

The dashboard's **Browse by category** section filters its stories by topic in
the reader's browser, together with the search box. It lists the categories of
the stories in the export, so a larger export (`--top 30`) gives each more stories.

The site's **Contested** page lists the latest stories whose coverage reports
a dispute, most contested first. That means headlines about accusations,
denials, rows, probes, arrests or protests, and quotes reported as criticism
or denial (`backend/analysis/contention.py`). Each card says what was counted.
It says nothing about which outlet is right. The page can only list stories
in the export, so add the latest contested ones to it:

```bash
python -m backend.scripts.export_review --top 14 --contested 10 --days 7
python -m backend.scripts.build_site
```

`--contested` alone builds a site of only those stories, and the dashboard
says so.

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
- **Model loading is the largest share of a run** — 54 s of a median 131 s
  passive run, over 93 runs since the 30 Sep optimisation. Every run over the
  5-minute limit was waiting on disk or on the feeds, not computing
  (`docs/evidence/evaluation-2026-10-15.md`). A long-lived worker would remove
  most of it.

Final-year project, Strathmore University.
