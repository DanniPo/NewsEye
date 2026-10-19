# Held-out evaluation - scored 2026-10-19 15:14

Sample drawn 2026-10-15T19:10:14 with seed 20261015 from data ingested after 2026-10-14T20:08:12+03:00 (code frozen at commit `6841847`). Thresholds were fixed before labelling. Intervals are 95% Wilson score intervals.

| Task | Labelled | Correct | Accuracy (95% CI) | Threshold | Verdict |
|---|---|---|---|---|---|
| quotes | 8 of 40 | 6 | 75% (41%-93%) | ≥ 90% | FAIL |
| roles | 40 of 40 | 37 | 92% (80%-97%) | ≥ 80% | PASS |
| names: Newseye | 40 of 40 | 31 | 78% (62%-88%) | ≥ 90% | FAIL |
| names: spaCy alone (baseline) | 40 of 40 | 22 | 55% (40%-69%) | baseline | - |

- Quotes by how they were shown: unattributed 1/1, attributed 5/7.
- Errors in quotes: unspecified 2.
- Errors in roles: speaks 2, acts 1.
- Names, paired on the same 40 headlines: Newseye right where spaCy alone was wrong in 10, the reverse in 1 (exact McNemar test p = 0.0117).
- Active tier on the 18 unseen stories: median 8.9s, slowest 28.3s; 18 of 18 within the 30 s requirement (NFR-01).
