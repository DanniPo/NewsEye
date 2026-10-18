# Test record - 2026-10-15 22:36

Commit `6841847` (with uncommitted changes) · Python 3.13.7 · torch 2.12.0+cu130 on NVIDIA T500 · 48s, of which 27s loading models

**144 of 144 cases passed** across 10 suites; 1 known limitation recorded, not counted; lint: 0 findings.

Regenerate with `python -m backend.scripts.test_record`. Each case lists what the code should produce and what it produced on this run. The cases are realistic sentences in the forms Kenyan outlets use; many are failures found on live data and kept as regression cases once fixed.

| Suite | Test IDs | Level · technique | Traces to | Passed | Time |
|---|---|---|---|---|---|
| `test_cluster_ids` | TC-CL-01 to -10 | Unit · white-box: one case per branch of the matching rule | FR-02 | 10/10 | 1.3s |
| `test_entities` | TC-EN-01 to -22 | Unit · black-box: real headline forms, plus names that must not become people | FR-03 | 22/22 | 2.0s |
| `test_coverage` | TC-CV-01 to -06 | Integration (MiniLM + NLI + set arithmetic) · black-box: hand-checked real pairs | FR-04, NFR-04 | 6/6 | 8.6s |
| `test_quotes` | TC-QT-01 to -21 | Unit · black-box: the attribution forms outlets use | FR-05 | 21/21 | 2.9s |
| `test_figures` | TC-FG-01 to -15 | Unit · black-box: pairs that must group and pairs that must not | FR-06 | 14/14 | 0.1s |
| `test_casualties` | TC-CS-01 to -15 | Unit · black-box: rival counts and misleading pairs | FR-06 | 15/15 | 0.1s |
| `test_portrayal` | TC-PT-01 to -18 | Unit · black-box: headline forms, including ones that must not read as speech | FR-07 | 18/18 | 1.1s |
| `test_targeted` | TC-TS-01 to -16 | Unit and integration · grey-box: a stand-in worker speaking the NewsMTSC worker's protocol; hand-worked metric examples | FR-07 | 16/16 | 3.2s |
| `test_divergence` | TC-DV-01 to -06 | Unit · black-box | FR-08 | 6/6 | 0.0s |
| `test_robustness` | TC-RB-01 to -16 | Unit and integration · grey-box: boundary values from the code's thresholds; failures injected at known dependencies | NFR-02, NFR-03 | 16/16 | 1.2s |
| `ruff check backend` | - | Static analysis | code quality | 0 findings | |

## Requirement coverage

Cases giving evidence for each requirement. A requirement with no case here is evidenced elsewhere: the end-to-end record, or the evaluation.

| Requirement | Cases | Passed |
|---|---|---|
| FR-01: Collect articles from the RSS feeds of 12 Kenyan outlets, de-duplicated, each with an embedding and a topic | 2 | 2 |
| FR-02: Group articles reporting the same event into stories that keep their id as news arrives | 12 | 12 |
| FR-03: Recognise Kenyan people, institutions and places | 22 | 22 |
| FR-04: Show which outlets carried each fact, which said something related, and which could not be read | 8 | 8 |
| FR-05: Show who was quoted and how each outlet's version of a remark differs | 24 | 24 |
| FR-06: Show each outlet's figures, side by side only when they count the same thing | 29 | 29 |
| FR-07: Show how each outlet presents a named person | 35 | 35 |
| FR-08: Point the reader to the stories where outlets differ most | 7 | 7 |
| FR-09: Publish a static site - dashboard, story, people and search pages - that can also be sent as one file | 1 | 1 |
| FR-10: Search the collection by meaning | - | - |
| NFR-01: Performance: passive run within 5 minutes; one story analysed within 30 s | - | - |
| NFR-02: Reliability: a failing feed, database or clustering is reported and never damages stored stories | 11 | 11 |
| NFR-03: Security: third-party feed content cannot inject markup or script; no credentials in the repository | 3 | 3 |
| NFR-04: Neutrality: no verdicts or scores; an outlet that could not be read is never counted as leaving anything out | 7 | 7 |

## Clustering: `test_cluster_ids`

Does a story keep its cluster id when the window is re-clustered?

Level and technique: Unit · white-box: one case per branch of the matching rule.

| Test ID | Traces to | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-CL-01 | FR-02 | identical run | cluster 0 keeps id 1, cluster 1 keeps id 2 | cluster 0 keeps id 1, cluster 1 keeps id 2 | PASS |
| TC-CL-02 | FR-02 | story grows from 2 to 6 articles | cluster 0 keeps id 1 | cluster 0 keeps id 1 | PASS |
| TC-CL-03 | FR-02 | oldest articles age out of the window | cluster 0 keeps id 1 | cluster 0 keeps id 1 | PASS |
| TC-CL-04 | FR-02 | two-article story swaps one article | cluster 0 keeps id 1 | cluster 0 keeps id 1 | PASS |
| TC-CL-05 | FR-02 | genuinely new story gets no id | cluster 0 keeps id 1, cluster 1 gets a fresh id | cluster 0 keeps id 1, cluster 1 gets a fresh id | PASS |
| TC-CL-06 | FR-02 | one stray article is not continuity | cluster 0 gets a fresh id | cluster 0 gets a fresh id | PASS |
| TC-CL-07 | FR-02 | split: larger half keeps the id | cluster 0 gets a fresh id, cluster 1 keeps id 1 | cluster 0 gets a fresh id, cluster 1 keeps id 1 | PASS |
| TC-CL-08 | FR-02 | merge: larger story's id survives | cluster 0 keeps id 2 | cluster 0 keeps id 2 | PASS |
| TC-CL-09 | FR-02 | no id is handed to two clusters | cluster 0 keeps id 1, cluster 1 gets a fresh id | cluster 0 keeps id 1, cluster 1 gets a fresh id | PASS |
| TC-CL-10 | FR-02 | empty history | cluster 0 gets a fresh id | cluster 0 gets a fresh id | PASS |

## NLP - names: `test_entities`

Does spaCy, with the Kenyan list and title rule, read Kenyan names correctly?

Level and technique: Unit · black-box: real headline forms, plus names that must not become people.

| Test ID | Traces to | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-EN-01 | FR-03 | the list: 107 people, one person per alias | no problems | no problems | PASS |
| TC-EN-02 | FR-03 | Former DP Gachagua hits back at Ruto's allies over the impeachment. | Gachagua = PERSON (rigathi-gachagua); Ruto = PERSON (william-ruto) | Gachagua = PERSON (rigathi-gachagua); Ruto = PERSON (william-ruto) | PASS |
| TC-EN-03 | FR-03 | Riggy G and Kalonzo met Jubilee officials at State House. | Riggy G = PERSON (rigathi-gachagua); Kalonzo = PERSON (kalonzo-musyoka); Jubilee = ORG (jubilee); State House = ORG (state-house) | Riggy G = PERSON (rigathi-gachagua); Kalonzo = PERSON (kalonzo-musyoka); Jubilee = ORG (jubilee); State House = ORG (state-house) | PASS |
| TC-EN-04 | FR-03 | Uhuru says Raila won as crowds gather at Uhuru Park. | Uhuru = PERSON (uhuru-kenyatta); Raila = PERSON (raila-odinga); Uhuru Park = FAC | Uhuru = PERSON (uhuru-kenyatta); Raila = PERSON (raila-odinga); Uhuru Park = FAC | PASS |
| TC-EN-05 | FR-03 | Matiang’i hits back at critics, and Fred Matiangi says he is ready. | Matiang’i = PERSON (fred-matiangi); Fred Matiangi = PERSON (fred-matiangi) | Matiang’i = PERSON (fred-matiangi); Fred Matiangi = PERSON (fred-matiangi) | PASS |
| TC-EN-06 | FR-03 | Ken Lusaka addressed residents before flights to Lusaka resumed. | Ken Lusaka = PERSON (ken-lusaka); not a person: Lusaka | Ken Lusaka = PERSON (ken-lusaka); Lusaka = ORG | PASS |
| TC-EN-07 | FR-03 | Deputy President Kithure Kindiki toured Embu. | Kithure Kindiki = PERSON (kithure-kindiki); Embu = GPE | Kithure Kindiki = PERSON (kithure-kindiki); Embu = GPE | PASS |
| TC-EN-08 | FR-03 | IEBC Chairperson Erastus Ethekon announced the new timetable. | IEBC = ORG (iebc); Erastus Ethekon = PERSON (erastus-ethekon) | IEBC = ORG (iebc); Erastus Ethekon = PERSON (erastus-ethekon) | PASS |
| TC-EN-09 | FR-03 | Winnie Odinga and Oburu Oginga spoke, while Odinga's legacy was recalled. | Winnie Odinga = PERSON (winnie-odinga); Oburu Oginga = PERSON (oburu-oginga); Odinga = PERSON | Winnie Odinga = PERSON (winnie-odinga); Odinga = PERSON; Oburu Oginga = PERSON (oburu-oginga) | PASS |
| TC-EN-10 | FR-03 | Students at Kenyatta University protested on Friday. | Kenyatta University = ORG (kenyatta-university); not a person: Kenyatta | Kenyatta University = ORG (kenyatta-university); Friday = DATE | PASS |
| TC-EN-11 | FR-03 | The patient was buried at Langata Cemetery on Sunday. | Langata Cemetery = FAC | Langata Cemetery = FAC; Sunday = DATE | PASS |
| TC-EN-12 | FR-03 | Leaders from Isiolo County backed the plan, said Senator Abdi Hassan Guyo. | Isiolo County = GPE; Abdi Hassan Guyo = PERSON | Isiolo County = GPE; Abdi Hassan Guyo = PERSON | PASS |
| TC-EN-13 | FR-03 | The man claims to be the son of late Nyeri Governor Nderitu Gachagua. | Nderitu Gachagua = PERSON | Nyeri = GPE; Nderitu Gachagua = PERSON | PASS |
| TC-EN-14 | FR-03 | Court directs the registry not to accept more petitions from man who claims to be late Nyeri Governor Nderitu Gachagua's son | Nderitu Gachagua = PERSON | Nyeri = GPE; Nderitu Gachagua = PERSON | PASS |
| TC-EN-15 | FR-03 | CS Wendot noted that the agency will manage the site. | Wendot = PERSON | Wendot = PERSON | PASS |
| TC-EN-16 | FR-03 | CS Mugaa and MP Wandeto toured Nyeri on Monday. | Mugaa = PERSON; Wandeto = PERSON; Nyeri = GPE | Mugaa = PERSON; Wandeto = PERSON; Nyeri = GPE; Monday = DATE | PASS |
| TC-EN-17 | FR-03 | Narok Governor Patrick ole Ntutu urged the evictees to wait. | Patrick ole Ntutu = PERSON; not a person: Patrick | Narok = GPE; Patrick ole Ntutu = PERSON | PASS |
| TC-EN-18 | FR-03 | Murang’a Governor Irungu Kang’ata has announced 2,048 job opportunities. | Irungu Kang’ata = PERSON | Murang’a = GPE; Irungu Kang’ata = PERSON; 2,048 = CARDINAL | PASS |
| TC-EN-19 | FR-03 | Lady Justice Diana Rachel Kavedza ruled on the matter. | Diana Rachel Kavedza = PERSON; not a person: Lady | Diana Rachel Kavedza = PERSON | PASS |
| TC-EN-20 | FR-03 | Governor Begins Probe Into Missing Funds | not a person: Begins Probe, Begins | no entities | PASS |
| TC-EN-21 | FR-03 | Ebola cases rise in DR Congo, says the Justice Ministry. | not a person: Congo, Ministry | DR = GPE; Congo = GPE; the Justice Ministry = ORG | PASS |
| TC-EN-22 | FR-03 | KURA will resurface the roads before the jubilee celebrations. | KURA = ORG (kura-acronym); not a person: jubilee | KURA = ORG (kura-acronym) | PASS |

## Analysis - coverage: `test_coverage`

Does the coverage table credit an outlet only with what it actually said?

Level and technique: Integration (MiniLM + NLI + set arithmetic) · black-box: hand-checked real pairs.

| Test ID | Traces to | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-CV-01 | FR-04, NFR-04 | different facts about the Ebola patient | Capital FM: related | Capital FM: related | PASS |
| TC-CV-02 | FR-04, NFR-04 | the same weapons, told two ways | Capital FM: reported | Capital FM: reported | PASS |
| TC-CV-03 | FR-04, NFR-04 | two different figures from one survey | Nairobi Wire: related | Nairobi Wire: related | PASS |
| TC-CV-04 | FR-04, NFR-04 | an outlet with nothing like the fact omitted it | Nation Africa: omitted | Nation Africa: omitted | PASS |
| TC-CV-05 | FR-04, NFR-04 | an outlet we could not read never omits | People Daily: neither | People Daily: neither | PASS |
| TC-CV-06 | FR-04, NFR-04 | known limit: the same auction with different details | Nairobi Wire: related | Nairobi Wire: related | PASS |

## Analysis - quotes: `test_quotes`

Does quote extraction find the words, the speaker, and how outlets differ?

Level and technique: Unit · black-box: the attribution forms outlets use.

| Test ID | Traces to | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-QT-01 | FR-05 | “We will not allow anyone to intimidate voters,” Kindiki said on Tuesday. | speaker Kithure Kindiki, verb say, how named | speaker Kithure Kindiki, verb say, how named | PASS |
| TC-QT-02 | FR-05 | Gachagua said: “The government is plotting to arrest me before the rally.” | speaker Rigathi Gachagua, how named | speaker Rigathi Gachagua, how named | PASS |
| TC-QT-03 | FR-05 | Treasury CS John Mbadi addressed traders in Mombasa on Monday. “The economy is recovering faster than expected,” he said. | speaker John Mbadi, how pronoun | speaker John Mbadi, how pronoun | PASS |
| TC-QT-04 | FR-05 | According to IEBC chairperson Erastus Ethekon, “the register will be audited before March.” | speaker Erastus Ethekon, verb according to | speaker Erastus Ethekon, verb according to | PASS |
| TC-QT-05 | FR-05 | “We are ready for the polls,” said Ethekon. | speaker Erastus Ethekon, how named | speaker Erastus Ethekon, how named | PASS |
| TC-QT-06 | FR-05 | “Investigations into the matter are ongoing,” the DCI said in a statement. | speaker Directorate of Criminal Investigations, how named | speaker Directorate of Criminal Investigations, how named | PASS |
| TC-QT-07 | FR-05 | “We have done our part. Parliament must now act,” Mbadi told reporters. | speaker John Mbadi, verb tell | speaker John Mbadi, verb tell | PASS |
| TC-QT-08 | FR-05 | “Nitapita asubuhi na mapema sana,” Mosiria said. | speaker Geoffrey Mosiria, language other | speaker Geoffrey Mosiria, language other | PASS |
| TC-QT-09 | FR-05 | The crowd chanted “Ruto must go home now” as police watched. | how unattributed | how unattributed | PASS |
| TC-QT-10 | FR-05 | Ruto pledged a ‘modern’ police force for the country. | no quote | no quote | PASS |
| TC-QT-11 | FR-05 | Deputy President Kithure Kindiki toured Embu on Monday. “We will vet all alcohol manufacturers afresh,” the DP said. | speaker Kithure Kindiki, how pronoun | speaker Kithure Kindiki, how pronoun | PASS |
| TC-QT-12 | FR-05 | President William Ruto commissioned the mausoleum of the late Raila Odinga in Bondo. “The site will now be run by the National Museums of Kenya,” he said. | speaker William Ruto, how pronoun | speaker William Ruto, how pronoun | PASS |
| TC-QT-13 | FR-05 | CS Wendot noted that the agency will manage the site to safeguard Raila's contributions. “The completion of the mausoleum marks an important milestone for the country,” she added. | speaker Wendot, how pronoun | speaker Wendot, how pronoun | PASS |
| TC-QT-14 | FR-05 | Interior CS Kipchumba Murkomen addressed residents in Eldoret on Monday. “We will not allow cattle rustlers to terrorise residents,” Murkomen said. “Additional officers have already been deployed to the affected areas.” | speaker Kipchumba Murkomen, how named | speaker Kipchumba Murkomen, how named | PASS |
| TC-QT-15 | FR-05 | The world marks the day under the theme “Adequate Housing for All” this week. | no quote | no quote | PASS |
| TC-QT-16 | FR-05 | an unattributed quote continues the last speaker | second quote: speaker Kipchumba Murkomen, how continued | second quote: speaker Kipchumba Murkomen, how continued | PASS |
| TC-QT-17 | FR-05 | the same remark, quoted alike | Nation Africa: same | Nation Africa: same | PASS |
| TC-QT-18 | FR-05 | one outlet trims the remark | Capital FM: says less | Capital FM: says less | PASS |
| TC-QT-19 | FR-05 | two different remarks are not lined up | nothing lined up | nothing lined up | PASS |
| TC-QT-20 | FR-05 | the same words under two names for one speaker | Nairobi Wire: same | Nairobi Wire: same | PASS |
| TC-QT-21 | FR-05 | an unattributed quote joins whoever another outlet credited | KBC: same | KBC: same | PASS |

## Analysis - figures: `test_figures`

Verify figure parsing and the subject/unit gate on realistic claim sets.

Level and technique: Unit · black-box: pairs that must group and pairs that must not.

| Test ID | Traces to | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-FG-01 | FR-06 | floods missing | grouped across two outlets | grouped: 1,300 (Nation), 1,500 (Standard) | PASS |
| TC-FG-02 | FR-06 | fdi vs foreign direct investment | grouped across two outlets | grouped: $2.8 billion (Business Daily), $3.2 billion (KBC) | PASS |
| TC-FG-03 | FR-06 | compliance deadline | grouped across two outlets | grouped: 60 (People Daily), 90 (Nairobi Wire) | PASS |
| TC-FG-04 | FR-06 | death toll | grouped across two outlets | grouped: 47 (Nation), 52 (KBC) | PASS |
| TC-FG-05 | FR-06 | inflation | grouped across two outlets | grouped: 4.5 per cent (Business Daily), 6.2 percent (Capital FM) | PASS |
| TC-FG-06 | FR-06 | same sum in two currencies | grouped across two outlets | grouped: £1.6bn (Capital FM), $2.1bn (Nation) | PASS |
| TC-FG-07 | FR-06 | seats won | grouped across two outlets | grouped: 39 (Nation), 47 (Capital FM) | PASS |
| TC-FG-08 | FR-06 | different things counted | kept apart | kept apart | PASS |
| TC-FG-09 | FR-06 | leaders vs trader days | kept apart | kept apart | PASS |
| TC-FG-10 | FR-06 | reforms vs days | kept apart | kept apart | PASS |
| TC-FG-11 | FR-06 | investment vs defence budget | kept apart | kept apart | PASS |
| TC-FG-12 | FR-06 | missing people vs unpaid teachers | kept apart | kept apart | PASS |
| TC-FG-13 | FR-06 | missing is not dead | kept apart | kept apart | PASS |
| TC-FG-14 | FR-06 | same figure, one source only | kept apart | kept apart | PASS |
| TC-FG-15 | FR-06 | hospitals built: claim vs audit | grouped across two outlets | kept apart - dropped by the 3x non-casualty spread cap | KNOWN |

## Analysis - figures: `test_casualties`

Does the figure digest group casualty counts that belong together?

Level and technique: Unit · black-box: rival counts and misleading pairs.

| Test ID | Traces to | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-CS-01 | FR-06 | road accident: police vs hospital | grouped: rival counts of one thing | grouped as people: 12 (Nation), 17 (Standard) | PASS |
| TC-CS-02 | FR-06 | protest: police vs rights group | grouped: rival counts of one thing | grouped as people: 3 (KBC), 11 (Nation) | PASS |
| TC-CS-03 | FR-06 | attack: military vs county officials | grouped: rival counts of one thing | grouped as people: 8 (KBC), 23 (Capital FM) | PASS |
| TC-CS-04 | FR-06 | building collapse: injured count | grouped: rival counts of one thing | grouped as people: 40 (Capital FM), 62 (People Daily) | PASS |
| TC-CS-05 | FR-06 | simultaneous reports, different tolls | grouped: rival counts of one thing | grouped as people: 3 (KBC), 11 (Nation) | PASS |
| TC-CS-06 | FR-06 | same place, two authorities | grouped: rival counts of one thing | grouped as people: 558 (K24 Digital), 826 (People Daily) | PASS |
| TC-CS-07 | FR-06 | spelled-out counts still compare | grouped: rival counts of one thing | grouped as people: five (KBC), eight (Capital FM) | PASS |
| TC-CS-08 | FR-06 | flood: missing count | grouped: rival counts of one thing | grouped as people: 1,300 (Nation), 1,500 (Standard) | PASS |
| TC-CS-09 | FR-06 | evolving toll, same incident | grouped: rival counts of one thing | grouped as people: 12 (Nation), 17 (Standard) | PASS |
| TC-CS-10 | FR-06 | dead is not injured | kept apart: side by side would mislead | kept apart | PASS |
| TC-CS-11 | FR-06 | dead is not missing | kept apart: side by side would mislead | kept apart | PASS |
| TC-CS-12 | FR-06 | different incidents | kept apart: side by side would mislead | kept apart | PASS |
| TC-CS-13 | FR-06 | cumulative vs single incident | kept apart: side by side would mislead | kept apart | PASS |
| TC-CS-14 | FR-06 | one outlet quoting two authorities | kept apart: side by side would mislead | kept apart | PASS |
| TC-CS-15 | FR-06 | parts of a disaster are not the whole | kept apart: side by side would mislead | kept apart | PASS |

## Analysis - people: `test_portrayal`

Does portrayal read who speaks, who acts and who is acted on?

Level and technique: Unit · black-box: headline forms, including ones that must not read as speech.

| Test ID | Traces to | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-PT-01 | FR-07 | Gachagua claims plot to arrest him ahead of rally | rigathi-gachagua: role speaks, verb claim, family claimed | rigathi-gachagua: role speaks, verb claim, family claimed | PASS |
| TC-PT-02 | FR-07 | Ruto: We will not tolerate graft in Kilifi | william-ruto: role speaks, family quoted directly | william-ruto: role speaks, family quoted directly | PASS |
| TC-PT-03 | FR-07 | Kalonzo: Uhuru was right to say Raila won | uhuru-kenyatta: role spoken about, by Kalonzo Musyoka | uhuru-kenyatta: role spoken about, by Kalonzo Musyoka | PASS |
| TC-PT-04 | FR-07 | MPs slam Ruto over the housing levy | william-ruto: role acted on, verb slam, by MPs | william-ruto: role acted on, verb slam, by MPs | PASS |
| TC-PT-05 | FR-07 | Ruku hits back at Gachagua over Kindiki coronation hat fall controversy | rigathi-gachagua: role acted on, verb hit back at, by Ruku | rigathi-gachagua: role acted on, verb hit back at, by Ruku | PASS |
| TC-PT-06 | FR-07 | Ipoa launches investigations into fatal shooting at Kindiki meeting in Nembure | kithure-kindiki: role mentioned | kithure-kindiki: role mentioned | PASS |
| TC-PT-07 | FR-07 | Kindiki launches affordable housing project in Embu | kithure-kindiki: role acts, verb launch | kithure-kindiki: role acts, verb launch | PASS |
| TC-PT-08 | FR-07 | Former Deputy President Rigathi Gachagua has accused the government of plotting chaos | rigathi-gachagua: role speaks, verb accuse, title former deputy president | rigathi-gachagua: role speaks, verb accuse, title former deputy president | PASS |
| TC-PT-09 | FR-07 | Waiguru rules out joining Gachagua’s DCP, cites Ngirici's treatment | rigathi-gachagua: role mentioned | rigathi-gachagua: role mentioned | PASS |
| TC-PT-10 | FR-07 | Gachagua was impeached by the Senate in October | rigathi-gachagua: role acted on, verb impeach | rigathi-gachagua: role acted on, verb impeach | PASS |
| TC-PT-11 | FR-07 | According to Interior CS Kipchumba Murkomen, the operation will continue | kipchumba-murkomen: role speaks, verb according to, title interior cs | kipchumba-murkomen: role speaks, verb according to, title interior cs | PASS |
| TC-PT-12 | FR-07 | DP Kindiki: No more importation of rice until locally produced crop is sold | kithure-kindiki: role speaks, family quoted directly, title dp | kithure-kindiki: role speaks, family quoted directly, title dp | PASS |
| TC-PT-13 | FR-07 | Atwoli tells Gachagua to stop invoking his name for political relevance | rigathi-gachagua: role acted on, verb tell, by Atwoli | rigathi-gachagua: role acted on, verb tell, by Atwoli | PASS |
| TC-PT-14 | FR-07 | Uhuru was right, says Kalonzo | uhuru-kenyatta: role described | uhuru-kenyatta: role described | PASS |
| TC-PT-15 | FR-07 | Wanga to Kalonzo: We loved you until you joined Gachagua | rigathi-gachagua: role spoken about, by Gladys Wanga | rigathi-gachagua: role spoken about, by Gladys Wanga | PASS |
| TC-PT-16 | FR-07 | Gachagua vs Uhuru: The battle for Mt Kenya after Ruto | rigathi-gachagua: any role but speaks | rigathi-gachagua: role mentioned | PASS |
| TC-PT-17 | FR-07 | 2027: How court puts IEBC under tighter rules on Ruto's poll results | william-ruto: any role but speaks | william-ruto: role mentioned | PASS |
| TC-PT-18 | FR-07 | Kioni Warns Gachagua: Stop ‘Ruining’ The United Opposition | rigathi-gachagua: role acted on, verb warn | rigathi-gachagua: role acted on, verb warn | PASS |

## Analysis - targeted tone: `test_targeted`

Does targeted scoring degrade safely, and do the evaluation tools count right?

Level and technique: Unit and integration · grey-box: a stand-in worker speaking the NewsMTSC worker's protocol; hand-worked metric examples.

| Test ID | Traces to | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-TS-01 | FR-07 | [client] stray output before ready, then two items in order | [0.6, -0.5] | [0.6, -0.5] | PASS |
| TC-TS-02 | FR-07 | [client] the model's own class | positive | positive | PASS |
| TC-TS-03 | NFR-02 | [client] the worker dies mid-run | [None, None], then unavailable without a retry | [None, None], then unavailable | PASS |
| TC-TS-04 | NFR-02 | [client] no NewsSentiment interpreter installed | [None], with the reason recorded | [None]; no NewsSentiment interpreter at 'C:\\Users\\HP\\AppData\\Loc | PASS |
| TC-TS-05 | FR-07 | [framing] PERSON with a span, an ORG, a PERSON without a span | targeted +0.6, sentence 0.0, sentence 0.0 | targeted +0.6, sentence +0.0, sentence +0.0 | PASS |
| TC-TS-06 | FR-07, NFR-02 | [framing] targeted on but the model missing | sentence for all three | sentence, sentence, sentence | PASS |
| TC-TS-07 | FR-07 | [framing] a span is used only while it still marks the entity | (0, 12), None, None | ((0, 12), None, None) | PASS |
| TC-TS-08 | FR-07 | [framing] two outlets, two mentions each, targeted on | each outlet scored_by targeted, positive | [('Capital FM', 'targeted', 'positive'), ('KBC', 'targeted', 'positive')] | PASS |
| TC-TS-09 | FR-07 | [claims] every recorded span points at its entity | all spans match | 6 spans, 0 mismatched | PASS |
| TC-TS-10 | FR-07 | [metrics] F1m, F1pn, accuracy on a worked example | (0.5, 0.75, 0.5) | (0.5, 0.75, 0.5) | PASS |
| TC-TS-11 | FR-07 | [metrics] Cohen's kappa: 75% agreement, 50% expected | 0.5 | 0.5 | PASS |
| TC-TS-12 | FR-07 | [metrics] tuning picks the perfect band nearest 0.15 | 0.2 | 0.2 | PASS |
| TC-TS-13 | FR-07 | [metrics] bootstrap: identical methods, then a perfect one | difference 0 with interval 0 to 0; then interval above 0 | +0.00 (+0.00 to +0.00); then +0.42 to +0.60 | PASS |
| TC-TS-14 | FR-07 | [sampler] 12 items from a big, a small and a middling outlet | all three outlets; at most 2 items per text; 1 text of the small outlet's article | ['Big', 'Mid', 'Small']; at most 2 per text; 1 item(s) from Small | PASS |
| TC-TS-15 | FR-07 | [sampler] what an annotator sees | no outlet column; the entity in [[ ]] | columns ['item', 'text', 'label', 'notes']; [[Ruto]] spoke. | PASS |
| TC-TS-16 | FR-07 | [agree] +1/+2 agree, -1/0 wait, x/x agree; then F002 settled | {'F001': ('agreed', 'positive'), 'F002': ('pending', ''), 'F003': ('agreed', 'x')}; then F002 ('settled', 'negative') | {'F001': ('agreed', 'positive'), 'F002': ('pending', ''), 'F003': ('agreed', 'x')}; then F002 ('settled', 'negative') | PASS |

## Output - dashboard: `test_divergence`

Does "where outlets differ" count only differences a reader can check?

Level and technique: Unit · black-box.

| Test ID | Traces to | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-DV-01 | FR-08 | omissions alone are not a difference | score 0 | score 0 | PASS |
| TC-DV-02 | FR-08 | related wording counts once per fact | related 1, score 1 | related 1, score 1 | PASS |
| TC-DV-03 | FR-08 | reworded and shortened quotes count, identical ones do not | quotes 2 | quotes 2 | PASS |
| TC-DV-04 | FR-08 | a wide tone gap about one person counts once | score 1 | score 1 | PASS |
| TC-DV-05 | FR-08 | a narrow tone gap does not | score 0 | score 0 | PASS |
| TC-DV-06 | FR-08 | two outlets with different death tolls | figures 1 | figures 1 | PASS |

## Edges - all stages: `test_robustness`

Do the edges hold: thresholds, failures, hostile input and empty input?

Level and technique: Unit and integration · grey-box: boundary values from the code's thresholds; failures injected at known dependencies.

| Test ID | Traces to | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-RB-01 | FR-07 | [boundary] tone label at the +/-0.15 neutral band | +0.15 neutral, +0.151 positive, -0.15 neutral, -0.151 negative | +0.15 neutral, +0.151 positive, -0.15 neutral, -0.151 negative | PASS |
| TC-RB-02 | FR-07 | [boundary] headline tone needs 4 sentences | 3: no tone given; 4: leans positive | 3: no tone given; 4: leans positive | PASS |
| TC-RB-03 | FR-05 | [boundary] a quote needs 4 words | 3 words: no quote; 4 words: quote | 3 words: no quote; 4 words: quote | PASS |
| TC-RB-04 | FR-02 | [boundary] a story keeps its id at exactly half shared | 2 of 4 shared: keeps id; 2 of 5 shared: fresh id | 2 of 4 shared: keeps id; 2 of 5 shared: fresh id | PASS |
| TC-RB-05 | FR-04, NFR-04 | [boundary] the loose-cluster warning starts below 0.50 coherence | 0.50: no warning; 0.49: warning | 0.50: no warning; 0.49: warning | PASS |
| TC-RB-06 | NFR-02 | [exception] database unreachable when the scheduled run starts | exit code 1, reported, no traceback | exit code 1 | PASS |
| TC-RB-07 | FR-01, NFR-02 | [exception] every feed answers HTTP 404 | 12 of 12 reported failed, 0 inserted | 12 of 12 reported failed, 0 inserted | PASS |
| TC-RB-08 | FR-02, NFR-02 | [exception] one cluster swallows 75% of the window | rejected, stored stories left alone | rejected, stored stories left alone | PASS |
| TC-RB-09 | NFR-03 | [security] only http(s) counts as a web link | http and https accepted; javascript:, data:, protocol-relative and empty rejected | all as expected | PASS |
| TC-RB-10 | FR-01, NFR-03 | [security] a feed item whose link is javascript: | not stored | 0 stored, 0 counted | PASS |
| TC-RB-11 | FR-09, NFR-03 | [security] a headline carrying markup and a javascript: link | markup shown as text; the unsafe link not rendered | clean | PASS |
| TC-RB-12 | FR-05, NFR-02 | [empty] quote extraction given nothing | [] | [] | PASS |
| TC-RB-13 | FR-05, NFR-02 | [empty] quote alignment given nothing | [] | [] | PASS |
| TC-RB-14 | FR-04, NFR-02 | [empty] coverage table given nothing | [] | [] | PASS |
| TC-RB-15 | FR-07, NFR-02 | [empty] framing given nothing | [] | [] | PASS |
| TC-RB-16 | FR-08, NFR-02 | [empty] divergence score given nothing | 0 | 0 | PASS |
