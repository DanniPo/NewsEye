# What switching would change: sentence tone against targeted sentiment

Run 2026-10-16 00:21 on the 300 unlabelled items in `eval\framing`. Sentence tone at ±0.15; targeted at ±0.29. **Not accuracy:** without labels this shows only where the methods disagree.

The methods put 138 of 300 items (46%) in different classes.

| Sentence \ targeted | negative | neutral | positive |
|---|---|---|---|
| negative | 33 | 75 | 3 |
| neutral | 3 | 73 | 26 |
| positive | 1 | 30 | 56 |

| Subset | Items | Different class |
|---|---|---|
| field: body | 47 | 21 (45%) |
| field: headline | 130 | 60 (46%) |
| field: snippet | 123 | 57 (46%) |
| entity_type: EVENT | 2 | 1 (50%) |
| entity_type: FAC | 2 | 2 (100%) |
| entity_type: GPE | 48 | 36 (75%) |
| entity_type: NORP | 14 | 5 (36%) |
| entity_type: ORG | 75 | 30 (40%) |
| entity_type: PERSON | 159 | 64 (40%) |

## Sharpest disagreements

| Text | Sentence | Targeted |
|---|---|---|
| Uganda’s [[Idi Amin]] and the East African act UNGA New York will never forget | negative (-0.53) | positive (+0.63) |
| ‘We have a better model than [[Uganda]],’ Ruto defends G-to-G fuel deal | positive (+0.67) | negative (-0.43) |
| In a statement on October 15, Karakacha condemned the increase and urged President [[William Ruto]] to honour his pledge to keep diesel prices in Mombasa low. | negative (-0.26) | positive (+0.77) |
| [[Benni McCarthy's]] professional loyalty to Kenya has placed the South African football icon at the centre of a rivalry increasingly playing out beyond t | neutral (+0.03) | positive (+0.91) |
| [[Ruto]] warns public debt, unfair global financial system threatens children welfare | negative (-0.80) | neutral (+0.07) |
| Anger over worsening insecurity spilt onto the streets of [[Isiolo]] on Thursday, September 17, 2026, after five people, including two police officers, we | negative (-0.88) | neutral (-0.01) |
| What Uhuru’s [[Azimio]] Resignation Means for Kalonzo’s Ukombozi Alliance | neutral (-0.03) | negative (-0.88) |
| [[Murkomen]]: Victims of banditry will not be compensated | negative (-0.85) | neutral (+0.01) |
| Bag ni ya nini? [[Rapper Kapitani]] and the music dreams bagging him | neutral (+0.02) | positive (+0.87) |
| [[NAIROBI]], Kenya, Oct 8 — At least 84 Kenyans have been killed or remain missing in connection with the Russia-Ukraine war, while a total of 354 Kenyan | negative (-0.83) | neutral (-0.00) |
| First Lady Mama [[Rachel Ruto]] has called for stronger international cooperation in tackling gender-based violence, femicide, human trafficking and th | neutral (+0.00) | positive (+0.83) |
| Uber, [[Bolt]] Warn Govt Plan Could Push Up Ride Costs by 35% | negative (-0.78) | neutral (+0.01) |
| Motorists Association Condemns EPRA Fuel Price Hike In a separate statement on October 15, [[the Motorists Association]] strongly condemned the latest petroleum price increases announced by EPRA, which will remain in effect until November 14, 2026. | negative (-0.68) | neutral (+0.10) |
| The [[ACA]] data shows that 19 per cent of the alcohol sold in the country is counterfeit. | negative (-0.77) | neutral (-0.01) |
| [[Ruto]] says Natembeya is undermining development projects funded by the national government. | negative (-0.72) | neutral (+0.02) |
