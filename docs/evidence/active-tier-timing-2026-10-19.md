# Active tier on the 18 held-out stories - 2026-10-19 14:50

Regenerate with the script in this record's history (analyze_cluster with refresh=True on each story in `docs/evidence/heldout/sample.json`). Live article fetches, same laptop (NVIDIA T500). The 15 Oct column is the same measurement before framing used NewsMTSC.

Models imported in 27.6 s; the NewsMTSC worker started in 12.0 s, once per batch.

**17 of 18 stories analysed. Median 6.3 s (15 Oct: 8.9 s), slowest 24.5 s (15 Oct: 28.3 s); 17 of 17 within the 30 s requirement.**

| Story | Seconds | 15 Oct (before NewsMTSC) | Articles | Readable | People compared | Outlet readings by NewsMTSC |
|---|---|---|---|---|---|---|
| 1159 | 14.6 | 28.3 | 2 | 1 | 0 | 0 |
| 1166 | 6.4 | 8.9 | 3 | 2 | 0 | 0 |
| 1175 | 7.1 | 11.5 | 3 | 2 | 2 | 0 |
| 1179 | 4.3 | 6.5 | 2 | 1 | 0 | 0 |
| 1180 | 4.6 | 6.2 | 2 | 2 | 0 | 0 |
| 1190 | 3.0 | 3.6 | 2 | 0 | 0 | 0 |
| 1192 | 6.6 | 10.2 | 3 | 2 | 0 | 0 |
| 1196 | 5.0 | 10.2 | 2 | 1 | 0 | 0 |
| 1200 | 18.1 | 9.9 | 6 | 2 | 1 | 2 |
| 1201 | 24.5 | 10.8 | 11 | 6 | 6 | 9 |
| 1202 | 6.7 | 7.2 | 4 | 0 | 1 | 2 |
| 1205 | 17.0 | 9.4 | 3 | 2 | 0 | 0 |
| 1216 | 6.3 | 13.2 | 2 | 2 | 0 | 0 |
| 1228 | 3.0 | 3.4 | 2 | 0 | 0 | 0 |
| 1233 | 3.1 | 4.0 | 2 | 0 | 0 | 0 |
| 1234 | 3.5 | 3.1 | 2 | 0 | 0 | 0 |
| 1236 | 5.1 | 4.9 | 2 | 1 | 0 | 0 |
| 1243 | failed: ClusterNotFound | 3.2 | | | | |

**Note on comparability.** The passive tier re-clustered on 19 Oct at 09:18, after the held-out sample was drawn. Story 1201 grew from 5 to 11 articles and 1200 from 5 to 6, which explains their longer times; story 1243 no longer exists. On the 13 stories whose article count did not change, the median is 5.0 s now against 6.5 s on 15 Oct. The first story in each run includes loading the NLI and sentence-tone models.
