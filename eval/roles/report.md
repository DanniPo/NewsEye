# Portrayal roles: rules against PropBank SRL

Run 2026-10-16 23:11. SRL: AllenNLP BERT SRL (structured-prediction-srl-bert, PropBank/OntoNotes), CPU, own environment. Regenerate with `python -m backend.eval.compare_roles run`.

## Portrayal test cases

Rules 18 of 18, hybrid with SRL 15 of 18. The cases were written for the rules, so this favours them; it shows where SRL fails on headline forms the rules were built for.

| Headline | Expected | Rules | Hybrid (SRL) |
|---|---|---|---|
| Gachagua claims plot to arrest him ahead of rally | speaks | speaks | speaks |
| Ruto: We will not tolerate graft in Kilifi | speaks | speaks | speaks |
| Kalonzo: Uhuru was right to say Raila won | spoken about | spoken about | spoken about |
| MPs slam Ruto over the housing levy | acted on | acted on | mentioned ✗ |
| Ruku hits back at Gachagua over Kindiki coronation hat fall controversy | acted on | acted on | acted on |
| Ipoa launches investigations into fatal shooting at Kindiki meeting in Nembure | mentioned | mentioned | mentioned |
| Kindiki launches affordable housing project in Embu | acts | acts | acts |
| Former Deputy President Rigathi Gachagua has accused the government of plotting chaos | speaks | speaks | speaks |
| Waiguru rules out joining Gachagua’s DCP, cites Ngirici's treatment | mentioned | mentioned | acted on ✗ |
| Gachagua was impeached by the Senate in October | acted on | acted on | acted on |
| According to Interior CS Kipchumba Murkomen, the operation will continue | speaks | speaks | mentioned ✗ |
| DP Kindiki: No more importation of rice until locally produced crop is sold | speaks | speaks | speaks |
| Atwoli tells Gachagua to stop invoking his name for political relevance | acted on | acted on | acted on |
| Uhuru was right, says Kalonzo | described | described | described |
| Wanga to Kalonzo: We loved you until you joined Gachagua | spoken about | spoken about | spoken about |
| Gachagua vs Uhuru: The battle for Mt Kenya after Ruto | not speaks | mentioned | mentioned |
| 2027: How court puts IEBC under tighter rules on Ruto's poll results | not speaks | mentioned | mentioned |
| Kioni Warns Gachagua: Stop ‘Ruining’ The United Opposition | acted on | acted on | acted on |

## 300 real mentions (drawn from 3,777)

Quote and colon handling decided 22 of them, the same for both. Of the 278 decided by the grammar step, the methods agree on 204 and differ on 74 (27%): snippet 32 of 123, headline 42 of 177. Agreement says nothing about which is right; the labelled disagreements do.

Rules (rows) against the hybrid (columns), grammar-step mentions only:

| rules \ hybrid | acted on | acts | described | mentioned | speaks | spoken about |
|---|---|---|---|---|---|---|
| acted on | 27 | 1 | 0 | 1 | 0 | 1 |
| acts | 3 | 57 | 0 | 7 | 1 | 0 |
| described | 0 | 0 | 2 | 0 | 0 | 0 |
| mentioned | 25 | 19 | 1 | 55 | 5 | 6 |
| speaks | 0 | 0 | 0 | 4 | 63 | 0 |
| spoken about | 0 | 0 | 0 | 0 | 0 | 0 |

## To finish

Mark `right` in `eval/roles/disagreements.csv` for each of the 74 rows: A, B, both or neither, judging only the marked person's role. The sheet does not say which option is which method. Then run `python -m backend.eval.compare_roles score`.
