# Live pipeline test - 2026-11-08 23:28

The scheduled pipeline (`backend/pipeline.py`: collect and group, compare, people
pages) run once against a copy of the database (`articles_livetest`, made with
`CREATE DATABASE ... TEMPLATE articles`), while the web API served that copy and
a probe acted as a reader. The real database was not touched, so every count
taken from it since 27 October 2026 still holds.

    DB_NAME=articles_livetest uvicorn backend.api.main:app --port 8000
    python <scratchpad>/live_probe.py probe.csv probe.stop     # every 3 s: health, the story list,
                                                               # sources, a story; a search every 30 s
    DB_NAME=articles_livetest python -m backend.pipeline --log pipeline-livetest.log

Same laptop as every other measurement (HP ZBook Firefly G8, NVIDIA T500 4 GB).

## The run

| Stage | Time | What it did |
|---|---|---|
| Collect and group (passive tier) | 224 s | 202 new articles from 11 feeds (Kenya News: feed unreachable, reported); grouping due, 34 stories and 107 unclustered articles in the 7-day window; 34 of 34 labelled |
| Compare (active tier) | 312 s | 14 stories with two or more outlets compared, 0 failed; median 10.1 s each, slowest 104 s |
| People pages | 160 s | 52 people rebuilt (the last build was 408 hours old) |
| **Whole run** | **696 s** | exit 0 |

The grouping keeps the last seven days, so after twelve days without a run every
October story ended: the published list went from 59 stories to 14. A reader
following a link to an ended story is told "We could not find that".

## What a reader saw meanwhile

783 requests over 695 s; every one answered 200 except one 404, for a story that
ended at the re-grouping (expected).

| Request | Answers | Median | 95th percentile | Slowest |
|---|---|---|---|---|
| `/api/health` | 191 | 0.018 s | 0.050 s | 0.67 s |
| `/api/stories?limit=100` | 191 | 0.037 s | 0.100 s | 0.18 s |
| `/api/sources` | 191 | 0.046 s | 0.101 s | 0.53 s |
| `/api/stories/{id}` | 189 | 0.057 to 0.241 s | 0.413 s | 0.53 s |
| `/api/search` | 20 | 0.061 s | 0.420 s | 41.6 s |

- New articles appeared as they were collected: 8,133 to 8,335 between 82 s and 220 s.
- The new grouping appeared all at once at 220 s, with no request seeing part of it.
- From 220 s to 533 s the new stories read "not compared yet" (14, then fewer as
  each comparison was saved, the last at 533 s): about five minutes in which the
  dashboard's stories have headlines but no comparison.
- The one slow search was the first, at 44 s, while the pipeline was loading its
  models on the same graphics card; every later search took about 0.06 s.
- Graphics memory peaked at 3,090 of 4,096 MB, during the comparisons.

## Afterwards

- The 8 end-to-end tests (`npm run e2e`) passed against the updated copy.
- The API's 63 cases and 17 live checks passed against it (`DB_NAME=articles_livetest
  python -m backend.scripts.test_api --live`).
- Two runs started together: the second reported "another run is still going" and
  changed nothing; the first finished (60 s: grouping not due, nothing to compare,
  people built 0.1 h earlier).
- The task `Newseye-Pipeline` was registered switched off
  (`backend/scripts/schedule_pipeline.ps1`), and `Newseye-Passive` left switched off.
