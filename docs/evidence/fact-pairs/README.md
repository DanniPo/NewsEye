# Fact pairs

Whether the sentences the coverage table groups as one fact really are one fact.

## 2026-10-08-recovered.csv: the development sample

The 30 pairs behind the development figure, with the mark each was given on 8 October 2026.

- **Judged by:** Claude, an AI assistant, alone.
- **Sentences:** cut to their first 150 characters, which is also all that was judged. The original
  files were not kept, so this was rebuilt from the session record on 6 November 2026.
- **Sample:** not random across the 64 pairs from 15 stories. It took 20 of the 52 pairs NLI split and
  10 of the 12 it kept.

| Measure | Result |
|---|---|
| Similarity alone: grouped pairs that are one fact | 13 of 30 = 43% (27% to 61%); about 33% weighted back to all 64 |
| With NLI: pairs still grouped that are one fact | 9 of 10 = 90% (60% to 98%) |
| Wrong merges | 17 of 30 before, 1 of 30 after |
| Real matches shown as "related" | 4 of the 13 marked; about half when weighted back to all 64 |
| Real matches shown as left out | None |

An earlier figure, 29 of 30 = 97%, counted every pair that was not a wrong merge, including the 20
NLI no longer groups. It did not measure what it was named as.

## sheet.csv and key.json: the fresh check, marked by the developer

Drawn on 6 November 2026 by `python -m backend.scripts.fact_pairs sample`, with full sentences and no
sign of what NLI decided: 15 of the 28 pairs NLI kept and 15 of the 72 it split, out of all 100
cross-outlet pairs matched by similarity in 59 stories. `key.json` says which pairs NLI kept.

- **Judged by:** the developer, from the full sentences. Claude did not see the marks before they
  were scored.
- **Marked:** all 30, on 9 November 2026. `note` was left empty.
- **Scored:** `python -m backend.scripts.fact_pairs score`, which wrote
  [fact-pairs-results-2026-11-09.md](../fact-pairs-results-2026-11-09.md).

| Measure | Result |
|---|---|
| Pairs NLI keeps as one fact that are one fact | 14 of 15 = 93% (70% to 99%) |
| Pairs NLI splits that are really one fact | 12 of 15 = 80% (55% to 93%) |
| Similarity alone: matched pairs that are one fact, weighted to all 100 | 84% |
| Real matches NLI keeps together, weighted | 31% |

What the table shows as one fact is nearly always one fact, but NLI shows about two-thirds of the
real matches as "said something related". None is shown as left out.

This disagrees with the development sample on the pairs NLI split: Claude marked 4 of 20 as real
matches, the developer 12 of 15. The samples differ in three ways: full sentences rather than the
first 150 characters, 100 pairs from 59 stories rather than 64 from 15, and who judged. Report this
check as the result, and the development sample as what guided the design.
