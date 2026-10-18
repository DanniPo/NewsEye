# Newseye: testing and evaluation

This document is source material for Chapter 5 (sections 5.4 and 5.5). Every
number in it comes from a record in `docs/evidence/`, and every record can be
regenerated with the command named beside it. Table and figure numbers follow
the report's Chapter 5 numbering. Renumber them if your chapter differs.

| Record | Command | Latest |
|---|---|---|
| Automated test cases | `python -m backend.scripts.test_record` | [test-record-2026-10-15](evidence/test-record-2026-10-15.md) |
| System test, feeds to site | `python -m backend.scripts.end_to_end` | [end-to-end-2026-10-15](evidence/end-to-end-2026-10-15.md). This run predates the ST test IDs; the next run adds them |
| Evaluation: intervals, repeated runs, figures | `python -m backend.scripts.evaluation` | [evaluation-2026-10-15](evidence/evaluation-2026-10-15.md) |
| Held-out evaluation | `python -m backend.scripts.heldout sample`, then `score` | Sheets in [evidence/heldout/](evidence/heldout/); **awaiting labels** |
| Usability test | Protocol in [usability-test-plan.md](usability-test-plan.md) | **Not yet run** |

---

## 5.4.1 Test strategy and acceptance criteria

**Purpose.** The tests show whether Newseye meets its requirements (Table 5.1).
Its main objective is to let a reader see what each Kenyan outlet reported
about one event, without the system issuing any verdict.

**Scope.**

- **In scope:** the whole pipeline (ingestion, clustering, the active-tier
  analysis and the static site) and its failure behaviour.
- **Out of scope:** the outlets' own websites, the internal accuracy of the
  pretrained models (they are tested only as used here), and load beyond one
  machine. The public site is static files, with no server, login or
  database, so authentication and server-side injection tests do not apply to
  it.

**Responsibilities.**

- The developer designed and ran every test, and labels the held-out sample.
  The names task is blinded (Section 5.4.3).
- The supervisor reviews the records.
- 5 to 8 volunteers take the usability test.

**Table 5.1: Requirements the tests trace to.** The same IDs are in
`backend/scripts/testkit.py` and in every record. Align them with Chapter 3 if
the numbering there differs.

| ID | Requirement |
|---|---|
| FR-01 | Collect articles from the RSS feeds of 12 Kenyan outlets, de-duplicated, each with an embedding and a topic |
| FR-02 | Group articles reporting the same event into stories that keep their id as news arrives |
| FR-03 | Recognise Kenyan people, institutions and places |
| FR-04 | Show which outlets carried each fact, which said something related, and which could not be read |
| FR-05 | Show who was quoted and how each outlet's version of a remark differs |
| FR-06 | Show each outlet's figures, side by side only when they count the same thing |
| FR-07 | Show how each outlet presents a named person |
| FR-08 | Point the reader to the stories where outlets differ most |
| FR-09 | Publish a static site (dashboard, story, people and search pages) that can also be sent as one file |
| FR-10 | Search the collection by meaning |
| NFR-01 | Performance: a passive run within 5 minutes; one story analysed within 30 s |
| NFR-02 | Reliability: a failing feed, database or clustering is reported and never damages stored stories |
| NFR-03 | Security: third-party feed content cannot inject markup or script; no credentials in the repository |
| NFR-04 | Neutrality: no verdicts or scores; an outlet that could not be read is never counted as leaving anything out |

**Table 5.2: Test levels and techniques.**

| Level | Question it answers | How | Technique |
|---|---|---|---|
| Unit | Does each component produce the right output? | 8 suites, 112 cases (TC-CL to TC-DV, without TC-TS) | Black-box: realistic sentences in the forms outlets use, many of them real failures kept as regression cases. White-box for cluster continuity: one case per branch of the matching rule. |
| Unit and integration, edges | Do thresholds, failures and hostile input behave as documented? | `test_robustness`, 16 cases (TC-RB) | Grey-box: boundary values taken from the code's thresholds; failures injected by replacing a known dependency (database, feed, clustering input) with one that fails |
| Integration | Do components agree at their interfaces? | Coverage suite (MiniLM + NLI + set arithmetic); CI job that builds the schema from an empty pgvector database; the system test's checks at each hand-off | Black-box |
| System | Does the whole pipeline work on live data? | `end_to_end`: feeds to database to clusters to analysis to site, 23 checks (ST) | Black-box, live workload |
| Performance and reliability | Is it fast and dependable enough over time? | 171 scheduled runs (20 Sep to 15 Oct); 18 held-out stories timed | Repeated measurement |
| Security | Can feed content attack a reader? Are secrets exposed? | TC-RB-09 to -11; review of SQL construction; scan of the git history | Negative testing plus manual review |
| Model evaluation | How accurate are the NLP components? | Development hand-checks against baselines; a held-out sample | Labelled sample, Wilson intervals, McNemar test |
| Acceptance and usability | Can intended readers use it as meant? | Task-based test with SUS | Planned, not yet run |

**Case types.**

- **Positive:** the cases that must group, tag or attribute.
- **Negative:** pairs that must stay apart (TC-FG-08 to -14, TC-CS-10 to -15),
  names that must not become people (TC-EN-19 to -22), and headlines that must
  not read as speech (TC-PT-16, -17).
- **Boundary:** TC-RB-01 to -05.
- **Exception:** TC-RB-06 to -08.
- **Empty input:** TC-RB-12 to -16.

**Table 5.3: Test environment.**

| Item | Value |
|---|---|
| Machine | Development laptop, Windows 11 Pro, NVIDIA T500 (4 GB) |
| Runtime | Python 3.13.7, torch 2.12.0+cu130 |
| Database | PostgreSQL 18.4, pgvector 0.8.2 |
| NLP | spaCy 3.8.16 with `en_core_web_sm` 3.8.0; transformers 5.17.0; sentence-transformers 6.0.1; hdbscan 0.8.44 |
| Models | `all-MiniLM-L6-v2`, `deberta-v3-base-zeroshot-v1.1-all-33` (topic and NLI), `twitter-roberta-base-sentiment-latest` |
| Tools | ruff 0.16.8; scipy 1.18.1 and matplotlib 3.11.1 for the evaluation; GitHub Actions (ubuntu-latest, Python 3.13, CPU torch) |

**Test data.**

- **Unit cases:** written by hand in the forms Kenyan outlets use.
- **System and performance tests:** the live feeds.
- **Held-out sample:** articles ingested after the code freeze.

All of it is published news: headlines, short quotes and public figures named
in reporting. Article bodies are fetched only for analysis and never stored.

**Table 5.4: Acceptance criteria, fixed before measurement.** The date each
was fixed matters, because a threshold chosen after seeing the result proves
nothing.

| Criterion | Threshold | Fixed |
|---|---|---|
| Automated regression cases | 100% pass; 0 lint findings | With the suites; enforced by CI |
| System test | Every hand-off check passes | 15 Oct 2026, before its first run |
| One story analysed (NFR-01) | ≤ 30 s | 15 Oct, before the 18 held-out stories were timed |
| Passive run (NFR-01) | ≤ 300 s | 15 Oct. The 171 logged runs predate it, so they are reported against it but were not run to meet it |
| Held-out quote speakers | ≥ 90% correct | 15 Oct, before any labelling |
| Held-out portrayal roles | ≥ 80% correct | 15 Oct, before any labelling |
| Held-out name tagging | ≥ 90% of headlines fully correct, and better than spaCy alone | 15 Oct, before any labelling |
| Usability | ≥ 80% task success; ≥ 80% comprehension; SUS mean ≥ 68 | 15 Oct, before any session |

---

## 5.4.2 Test cases, defects and retesting

There are 145 automated cases in 10 suites. Table 5.5 summarises them by module in the
template's format. Each case's own scenario, expected result and actual result
is in the [test record](evidence/test-record-2026-10-15.md).

**Table 5.5: Test cases and results.**

| Test ID | Traceability | Scenario, data and conditions | Expected result | Actual result, evidence and verdict |
|---|---|---|---|---|
| TC-CL-01 to -10 | FR-02 | Stored and new cluster memberships: identical, grown, aged out, split, merged, a stray article, empty history | Each new cluster inherits the right old id, or a fresh one; no id handed to two clusters | 10/10 as expected; test record. **Pass** |
| TC-EN-01 to -22 | FR-03 | 21 sentences with Kenyan names, titles, namesakes, places and ambiguous words; the entity list itself | Each name found with the right type and identity; nothing invented; no alias naming two people | 22/22; test record. **Pass** |
| TC-CV-01 to -06 | FR-04, NFR-04 | Real cross-outlet sentence pairs that were checked by hand, including an unreadable outlet | Each outlet marked reported, related, omitted or not applicable, as hand-checked | 6/6; test record. **Pass** |
| TC-QT-01 to -21 | FR-05 | 15 attribution forms, a continued quote, 5 cross-outlet alignments | Right speaker and attribution type; versions compared as same, says less or reworded | 21/21; test record. **Pass** |
| TC-FG-01 to -15 | FR-06 | 7 figure pairs that must group, 7 that must not, 1 known limitation | Grouped or kept apart as listed | 14/14 counted; the known limitation (TC-FG-15, claim against audit) is still not grouped and stays recorded. **Pass** |
| TC-CS-01 to -15 | FR-06 | 9 rival casualty counts; 6 misleading pairs (dead against injured, different incidents) | Rivals grouped, misleading pairs kept apart | 15/15; test record. **Pass** |
| TC-PT-01 to -18 | FR-07 | Headline forms: speech, action, acted on, mention; Title Case; "X vs Y" | The right role, verb, actor and title for the person | 18/18; test record. **Pass** |
| TC-TS-01 to -17 | FR-07, NFR-01, NFR-02 | A stand-in worker speaking the NewsMTSC worker's protocol: stray output, a worker dying mid-run, a missing interpreter, a stopped worker with cached scores; stale spans; worked metric examples; the framing sampler and agreement | Scores in order; every failure falls back to sentence tone; cached scores still served; metrics match hand calculation | 17/17; test record. **Pass** |
| TC-DV-01 to -06 | FR-08 | Small stored analyses with omissions, related wording, quotes, tone gaps and figures | Only checkable differences counted | 6/6; test record. **Pass** |
| TC-RB-01 to -05 | FR-02, -04, -05, -07 | Values exactly at a threshold: tone ±0.15, 4 tone sentences, 4-word quote, half-shared story, 0.50 coherence | Each falls on its documented side | 5/5; test record. **Pass** |
| TC-RB-06 to -08 | NFR-02 | Database unreachable; all 12 feeds answer 404; one cluster holding 75% of the window | Reported with an exit code; feeds listed as failed; clustering rejected, stored stories untouched | 3/3; test record. **Pass** |
| TC-RB-09 to -11 | NFR-03 | Feed links with `javascript:` and `data:` schemes; a headline carrying `<script>` and `<img onerror>` | Unsafe links neither stored nor rendered; markup shown as text | 3/3 after DEF-27. Before the fix, 2 of these failed (see the defect log). **Pass** |
| TC-RB-12 to -16 | NFR-02 | Every analysis step given empty input | An empty result, no error | 5/5; test record. **Pass** |
| ST (23 checks) | FR-01, -02, -04 to -10, NFR-02 | Live run on 15 Oct: 12 feeds, 2,121 articles in the window, 5 new stories followed through (3 with two or more readable outlets got pages; 2 correctly got none) | Every hand-off holds: articles have embeddings and topics; ids continue; analyses saved; pages complete; search covers the database | 23/23; [end-to-end record](evidence/end-to-end-2026-10-15.md). **Pass** |
| PERF-01 | NFR-01 | One story through the active tier: 18 held-out stories, live fetches, same laptop | ≤ 30 s each | Median 9.4 s, slowest 28.3 s, 18/18 within; `heldout/sample.json`. **Pass** |
| PERF-02 | NFR-01 | Scheduled passive runs: 93 since the 30 Sep optimisation, live feeds | ≤ 300 s | 82/93 (88%) within; median 131 s; [evaluation](evidence/evaluation-2026-10-15.md). **Fail for 11 runs**, each waiting on disk or network (Section 5.4.3) |
| REL-01 | NFR-02 | All 171 scheduled runs, 20 Sep to 15 Oct | Every run finishes or reports its failure | 169 completed every stage; 2 stage failures reported and the run exited; 2 offline runs exited cleanly. **Pass** |
| SEC-01 | NFR-03 | The git history of all branches, searched for passwords, keys and tokens | No credential committed | None found. The database password is read from an environment variable. **Pass** |
| SEC-02 | NFR-03 | Review of every SQL statement | Values reach SQL only as bound parameters | All values are bound. The five f-string queries insert only fixed fragments from the code. **Pass** |
| UAT-01 to -08 | FR-04, -05, -06, -07, -09, -10, NFR-04 | Usability tasks T1 to T6 and comprehension checks C1 and C2 | See Table 5.4 | **Not yet run** |

**Defects and retesting.** Each row records a defect: what should have
happened, what actually happened, the correction, and the evidence that it is
fixed. A failed result is never deleted when a later version passes. Rows
marked "no regression case" were fixed and checked once, but no automated case
guards them yet.

**Table 5.6: Defect log.**

| ID | Component | Found by | Expected | Actual (before) | Correction | Retest |
|---|---|---|---|---|---|---|
| DEF-01 | Passive tier | Run log | Re-cluster after 40 new articles or 20 h | Clustered on every run: it counted unclustered articles, and HDBSCAN leaves about half the window as noise | Count articles since the last clustering (`clustered_at`) | 47 of 93 runs since the fix clustered; the rest skipped as not due |
| DEF-02 | Passive tier | Timing a run | About 2 minutes per run | A 139 s run took over 11 minutes under Task Scheduler's default I/O throttling | Register `pythonw.exe` at normal priority | Median 263 s before the fix, 131 s after (PERF-02) |
| DEF-03 | Passive tier | Run log | Reported time reflects work | One run reported 11,632 s with the laptop asleep | Per-stage timings, with unaccounted time named separately | Every run since logs stage times |
| DEF-04 | Ingestion | Missing outlet | A dead feed is reported | People Daily's 403 was skipped silently | `FEED FAILED` logged; failures returned to the caller | TC-RB-07; ST-02 |
| DEF-05 | Clustering | Broken links | A story keeps its id across runs | New ids every run: links broke and analyses were discarded | `match_clusters` (≥ half of the smaller story shared) | TC-CL-01 to -10, TC-RB-04; 440 of 445 kept their id on 15 Oct |
| DEF-06 | Database | Checking dates | `clustered_at` is a story's last clustering | `ADD COLUMN DEFAULT now()` stamped existing rows with the migration time | Add, backfill from `created_at`, then set the default | No regression case |
| DEF-07 | Names | Hand-check of 522 headline mentions | Kenyan names tagged correctly | spaCy alone: 26% correct, 35% wrong type, 39% missed | Entity list (107 people, institutions, 47 counties) and a title rule | TC-EN-01 to -22; 98% in-sample; held-out pending |
| DEF-08 | Names | Test case | "Patrick ole Ntutu" is one person | Tagged "Patrick" | List and title rule moved after NER; name particles kept | TC-EN-17 |
| DEF-09 | Names | People page | A namesake is not the listed person | "Nderitu Gachagua" inherited Rigathi Gachagua's id | Entity ids reset before reassignment | TC-EN-13, -14 |
| DEF-10 | Names, quotes | Quote hand-check | "CS Wendot … she added" is Wendot | spaCy read "CS Wendot" as an organisation; "she" went to Raila Odinga | Title-plus-name clash resolved to a person | TC-EN-15, TC-QT-13 |
| DEF-11 | Quotes | Quote hand-check | "he said" is whoever spoke or acted | Attributed to the late Raila Odinga, who was only mentioned | Pronouns resolve to the nearest speaker or actor | TC-QT-12 |
| DEF-12 | Portrayal | People page | "Gachagua vs Uhuru: …" is not Gachagua speaking | Read as speech; "joining Gachagua’s DCP" read as joining him | "Name: words" counts as speech only after a name with its titles; curly apostrophes normalised | TC-PT-16, TC-PT-09 |
| DEF-13 | Portrayal | People page | Titles describe the person | "former Ruto ally" gave Ruto a title; "Confronts" read as a title | Modifier words are not titles | No regression case |
| DEF-14 | Portrayal | Test case | Title Case headlines parse correctly | spaCy misread "Kioni Warns Gachagua: …" | Sentence case restored from how words appear in snippets | TC-PT-18 |
| DEF-15 | Coverage | Hand-check of 30 pairs | An outlet credited only with its own fact | Similarity merged 17 of 30 different facts | NLI checks each match both ways; "related" state added | TC-CV-01 to -06; 1 of 30 after |
| DEF-16 | NLI | Re-reading a result | An identical pair scores as entailment | Recorded as "contradiction 0.853" | Labels read from the model's config (2 labels, entailment first) | TC-CV-02 relies on it |
| DEF-17 | Figures | Rewritten tests | A death toll is not set against an injury count | Grouped as rival counts | Casualty state must match | TC-CS-10 |
| DEF-18 | Tests | Review of a passing case | "Different incidents" kept apart for the right reason | It passed only because "Seven" was not parsed | Entities attached as in production; spelled-out counts parsed | TC-CS-12, TC-CS-07 |
| DEF-19 | Tests | Preparing the record | A failing casualty case fails CI | `test_casualties` always exited 0 | Exits 1 on any failure | Exit code checked on 15 Oct |
| DEF-20 | Framing | Divergence review | Tone comparisons are informative | "Kenya" made 5 of 11 tone divergences | Terms found across most clusters excluded | No regression case |
| DEF-21 | Framing | Page review | A sentence's label describes that sentence | The outlet's average label was shown beside it | Each example carries its own label | No regression case |
| DEF-22 | Framing | Page review | Entities are names | "Martin Kimani Lands Top Job" treated as a name | Spans over 4 words or containing a verb rejected | No regression case |
| DEF-23 | Export | Demo review | A page compares one event | 3 of 13 pages were loose clusters (coherence 0.445 to 0.464) | 0.50 coherence floor applied in the export | TC-RB-05 (warning boundary) |
| DEF-24 | Coverage table | Demo review | Each outlet appears in one column | An outlet appeared as both read and unread | Unread outlets exclude read ones | No regression case |
| DEF-25 | Dashboard | Ranking review | The ranking separates stories | "Facts not carried by all" was 100% in half the stories | Only checkable differences counted | TC-DV-01 |
| DEF-26 | Showcase | Picker output | "Hits back" signals a dispute | "hits" matched "milk output hits 5.2B litres" | Phrase-only matching | No regression case |
| DEF-27 | Ingestion, site | Security review, 15 Oct | Only http(s) links reach a reader | On commit `6841847`: a feed link `javascript:alert(document.cookie)` was stored (12 of 12 feeds) and rendered as `href="javascript:…"`. HTML escaping already worked. No stored link was affected (0 of 7,367) | Links checked at ingestion (`is_web_url`) and again when the site is built; unsafe links shown as plain text | TC-RB-09 to -11 pass; the same cases fail on the old commit |
| DEF-28 | Targeted worker | Integration smoke test, 15 Oct | The worker's pipe carries only answers | NewsSentiment prints a download line straight to stdout; the client crashed reading it | Worker points descriptor 1 at stderr; client skips stray lines | TC-TS-01 (the stand-in prints the same line first) |
| DEF-29 | Framing sampler | Inspecting the first draw | Body sentences and people represented | 0 of 300 items from body text; 32% people | Turns per outlet and field; 60% of items from texts naming a person | Redraw: 47 body items, 159 people (53%) |
| DEF-30 | Targeted worker | First start, 15 Oct | No unannounced 584 MB download inside a pipeline step | Missing weights started a download the 20-minute load timeout would kill | Worker refuses to start without weights and names the download command | Refused in 10 s with the command |
| DEF-31 | Quotes | Preparing the Chapter 5 figures, 16 Oct | After "Ruto has described Kenyatta as the most ungrateful…", "he said" is Ruto | KBC's version of the remark was given to Kenyatta, the person described, and headed the remark on the story page; Capital FM's version correctly says Ruto | Open: resolve a pronoun to the reporting sentence's subject before its object; flag a remark whose versions name different speakers | Checked against both articles; not yet retested |

Some features were also removed because measurement showed they did not work
on this corpus (Table 5.7). These are design decisions, not defects.

**Table 5.7: Features removed after measurement.**

| Feature | Measured on | Result | Decision |
|---|---|---|---|
| Contradiction detection | 151 story groups | 0 genuine contradictions between outlets | Reframed around what each outlet included and left out |
| Figure-conflict adjudication | 800 and 2,162 articles | 0 true positives; every firing was a scope mismatch | Replaced by the figure digest: shown in context, never adjudicated |
| Stance classification | Live headlines | "Appoints Kenyan Diplomat to Crucial New Role" called critical at 0.796 | Removed |
| Abstractive summaries | 149 summaries | Names misspelled in 77 (52%, 95% CI 44% to 60%) | Extractive headline: copies names, cannot misspell them |
| People named, as a story-ordering signal | 12, then 63 stories | ρ +0.42 at n = 12; −0.16 at n = 63 | Kept ordering by number of outlets |

---

## 5.4.3 Project-type-specific evaluation

Newseye is an AI/ML system that serves a decision-support purpose: it informs
a reader's own judgement. So both kinds of evidence apply: model accuracy
against baselines, and usability.

**Comparison with baselines (development samples).** Each change was measured
against what it replaced, on the same items (Table 5.8, Figure 5.1). These
samples drove development, so they show the size of each improvement, not
performance on unseen data. The name result is in-sample by construction: the
list was built from the same corpus.

**Table 5.8: Development accuracy against baselines** (95% Wilson intervals).

| Task | Baseline | Newseye | Items |
|---|---|---|---|
| Listed names tagged correctly in headlines | spaCy alone, 26% (22% to 30%) | 98% (97% to 99%), in-sample | 522 mentions |
| Unlisted names after a title tagged as people | Without the title rule, 82% (74% to 89%) | 93% (87% to 97%) | 102 mentions |
| Pairs grouped as one fact that are one fact | Similarity alone, 43% (27% to 61%) | 97% (83% to 99%); false omissions 0 | 30 pairs |
| Quote speaker right, three successive samples | – | 80% (63% to 90%) → 90% (71% to 97%) → 96% (81% to 99%) | 30, 21, 26 |
| Portrayal role right | – | 85% (71% to 93%) | 40 mentions |

*Figure 5.1: Development accuracy against baselines, with 95% intervals.*
![Figure 5.1](figures/fig-dev-accuracy.png)

**Held-out test (the final measure of model accuracy).**

- **Sample:** drawn on 15 Oct with a fixed seed. Every item comes from articles
  ingested after commit `6841847` (14 Oct, 20:08). The quote, portrayal and
  entity code has not changed since that commit, so no item influenced it.
- **Pools:** 45 quotes from the 18 unseen multi-outlet stories, 371 person
  mentions and 360 headlines. 40 items were drawn from each.
- **Names task:** each headline shows spaCy alone and Newseye side by side, in
  an order shuffled per row and recorded in a hidden key. The labeller cannot
  tell which system produced which tagging. The two systems are compared on the
  same headlines with an exact McNemar test.
- **Status:** the sheets are ready, and
  `python -m backend.scripts.heldout score` turns the labels into accuracy with
  intervals and a verdict against Table 5.4. Report these results, not the
  development figures, as the system's accuracy.
- **Limit:** the coverage table cannot be held-out tested. A stored analysis
  keeps each fact's anchor sentence but not the other outlets' matching
  sentences, so a labeller cannot judge a merge. Storing them would make this
  possible.

**Error analysis.**

- **NFR-01, passive runs:** all 11 runs over 5 minutes since the optimisation
  were dominated by waiting, not computation. Seven were model loading
  (importing torch from disk, up to 2¼ hours with the laptop asleep) and four
  were feed downloads. Clustering and summarising stayed under 12 s in every
  one. A long-lived worker that keeps the models loaded would remove the
  larger cause.
- **Feeds:** across 169 online runs, Nation Africa failed in 14 (92%
  available; 13 of those were HTTP 404 while its feed address was broken) and
  Kenya News in 9 (95%, all network errors reaching its server).
- **Models:** error categories will come from the held-out labels (the `error`
  and `right_role` columns).

**Variation.**

- **Accuracy:** every proportion is reported with a 95% interval. Samples of 20
  to 40 give wide intervals, so differences within them are not claimed.
- **Clustering:** HDBSCAN is deterministic on the same data. Across live
  re-clustering, stories kept their ids: 342 of 348 in one run, and 440 of 445
  on 15 Oct.
- **Performance:** the distribution over 171 runs is in Figure 5.2.

**Framing: sentence tone against targeted sentiment** ([benchmark](../eval/framing/benchmark.md)).
Story pages and people pages scored how outlets present a person by the tone
of whole sentences. NewsMTSC's GRU-TSC (Hamborg and Donnay, 2021) scores the
writer's attitude toward the marked person instead. Both were scored on
NewsMTSC's human-labelled test sets, thresholds tuned on dev only, against a
decision rule fixed before the run.

| Method (test, F1m) | rw (803 targets) | mt (1,034 targets) |
|---|---|---|
| Sentence tone, dev-tuned | 0.660 | 0.628 |
| Targeted, dev-tuned (adopted) | 0.811 | 0.826 |
| Targeted, its own most likely class | 0.830 | 0.826 |
| Combined: stacked model over both | 0.831 | 0.831 |

Targeted minus sentence: +0.150 (95% CI +0.113 to +0.189) and +0.199 (+0.167 to
+0.232): the rule is met, so people are now scored targeted, threshold ±0.29.
Combining the two did not beat the single model on both sets: the tuned blend
put all its weight on targeted, and the stacked model gained +0.021 on rw
(+0.001 to +0.040) but +0.004 on mt (−0.011 to +0.020). On the 300-mention
Kenyan sample the methods disagree on 46% of mentions, mostly targeted moving
event tone to neutral; its labels, from two annotators, confirm or revert the
switch. Caveats: in-domain for GRU-TSC, US news, headlines outside its training
data.

**Human-centred evaluation.** Usability, task completion and the reader's
reading of the "could not read" and tone signals are planned
([protocol](usability-test-plan.md)) and not yet measured.

---

## 5.4.4 Results and interpretation

*Figure 5.2: Wall-clock time of every scheduled passive run, 20 Sep to 15 Oct
2026. Runs before 30 Sep include Task Scheduler's I/O throttling and the laptop
sleeping mid-run.*
![Figure 5.2](figures/fig-passive-runtime.png)

*Figure 5.3: Coherence of the 445 stories in the 7-day window on 15 Oct; 52
(12%) fall below the 0.50 floor and get no page.*
![Figure 5.3](figures/fig-coherence.png)

**Table 5.9: Requirements against evidence.**

| Requirement | Evidence | Status |
|---|---|---|
| FR-01 | ST ingest checks 4/4; TC-RB-07, -10; 169 of 171 runs completed | Met |
| FR-02 | TC-CL 10/10; TC-RB-04, -08; 440 of 445 ids kept | Met |
| FR-03 | TC-EN 22/22; development 98% (in-sample) and 93% | Met on test cases; held-out pending |
| FR-04 | TC-CV 6/6; 29 of 30 pairs; no false omissions | Met on test cases; no held-out measure possible yet |
| FR-05 | TC-QT 21/21; development 96% | Met on test cases; held-out pending |
| FR-06 | TC-FG 14/14 (1 known limitation); TC-CS 15/15 | Met on test cases; no live accuracy measure |
| FR-07 | TC-PT 18/18; TC-TS 17/17; development 85%; targeted sentiment beat sentence tone by +0.150 and +0.199 F1m on NewsMTSC | Met on the benchmark and switched to targeted; held-out roles and Kenyan framing labels pending |
| FR-08 | TC-DV 6/6; outlets against differences ρ +0.40 (+0.17 to +0.59) | Met |
| FR-09 | ST publish checks; TC-RB-11; 56-page single file, no broken links | Met |
| FR-10 | Search index covers all 7,339 articles (ST) | Partly: search relevance not evaluated |
| NFR-01 | One story: 18/18 within 30 s; with targeted framing 6 to 8 s per story after a one-time 30 s worker start. Passive: 88% of runs within 5 min | Partly: the first story in a process, and overruns that are I/O |
| NFR-02 | TC-RB-06 to -08, -12 to -16; REL-01 | Met |
| NFR-03 | TC-RB-09 to -11 (after DEF-27); SEC-01, SEC-02 | Met |
| NFR-04 | TC-CV-05; TC-RB-05; no score or verdict anywhere on the site | Met in the system; reader comprehension pending (C1, C2) |

**Interpretation.**

- **The core workflow works end to end on live data,** and its components
  agree at every interface checked.
- **Correctness is strongest where it can be stated exactly:** story
  continuity, figure gating, failure handling and link safety.
- **The NLP components improved substantially on their baselines during
  development,** but those measurements were taken on the data that shaped
  them. Until the held-out sample is labelled, no accuracy claim should be
  generalised.
- **All results apply to this corpus, 12 Kenyan outlets over September and
  October 2026, and to one laptop.** They do not show how Newseye would
  perform on other outlets, languages or hardware.

---

## 5.5 Version control and implementation evidence

**Project repository:** [github.com/DanniPo/NEWSEYE](https://github.com/DanniPo/NEWSEYE).
Make sure your supervisor can open it, either because it is public or because
they have been added as a collaborator.

**What the repository already shows.**

- **README:** the problem, setup, configuration, how to run it, and test
  instructions.
- **Environment files:** `requirements.txt`, `requirements-dev.txt` and
  `pyproject.toml`.
- **Reproducibility:** `.gitignore` excludes the virtual environment, logs,
  exports and built files. The database password comes from an environment
  variable (`.env.example`), and no credential has ever been committed
  (SEC-01).
- **Continuous integration:** every push runs lint, imports, all 10 suites, and
  a schema build from an empty database.
- **Branching:** development happens on `test` and reaches `main` through a
  pull request (PR #1, 30 Sep).

**What is missing, and what to do.**

| Gap | Action |
|---|---|
| The last 3 commits on `test` (30 Sep to 14 Oct) are not on GitHub, so the supervisor cannot see the optimisation, NLI or entity work | Push `test`, then open a pull request into `main` |
| Several early commit messages say nothing ("commit", "fixes and such", "new fixes") | Do not rewrite pushed history. Write descriptive messages from now on, and explain the early ones in the report |
| No release tags | Tag milestones, for example `v0.1-progress-review` and `v1.0-submission` |
| No licence or access statement | Add a `LICENSE`, or a statement of the university's terms, after checking Strathmore's policy on student project IP |
| No issues or other task record | Open an issue for each pending item: held-out labelling, usability test, FR-10 search evaluation, a long-lived worker for NFR-01. Close each with the commit that resolves it. Future defects can be issues that the defect log references |

**Explaining the workflow in the report.**

- **`test` branch:** keeps experiments, such as the NLI coverage check and
  entity-list tuning, away from `main` until they pass CI.
- **Pull requests:** each one is a reviewable milestone.
- **CI:** it stopped regressions reaching `main`. After DEF-19 it can also
  catch figure-digest regressions.
- **Commit history:** shows each defect in Table 5.6 being fixed, alongside the
  test that guards it.
