# Framing benchmark: sentence tone against targeted sentiment

Run 2026-10-15 23:58. Regenerate with `python -m backend.eval.benchmark_framing`.

**Decision rule, fixed before the first run.** Switch PERSON mentions to targeted scoring if, on both the rw and the mt test set, the targeted method with its dev-tuned threshold has a higher F1m than the sentence method with its dev-tuned threshold, and the paired 95% bootstrap interval of the difference lies wholly above zero. The production threshold is then the targeted method's, tuned on the rw dev split. A combined method (a blend of both scores, or a stacked model over both, each fitted on dev alone) replaces targeted only if it beats the dev-tuned targeted method on F1m on both test sets the same way; otherwise the single model stays, as the simpler of two equals.

## Data

NewsMTSC (Hamborg & Donnay, 2021), the dev and test splits the authors used. Gold labels are the authors' human annotations: the writer's attitude toward the marked person. *rw* follows the real-world distribution of sentiment in news; in *mt* every sentence names at least two people.

| Set | Split | Sentences | Targets | Gold classes | SHA-256 |
|---|---|---|---|---|---|
| rw | dev | 320 | 343 | negative 134, neutral 136, positive 73 | `d62a327eefa1` |
| rw | test | 747 | 803 | negative 295, neutral 319, positive 189 | `64a6e2619734` |
| mt | dev | 216 | 442 | negative 136, neutral 217, positive 89 | `728602b11d63` |
| mt | test | 505 | 1034 | negative 346, neutral 531, positive 157 | `765cb5979353` |

Sentence method: `cardiffnlp/twitter-roberta-base-sentiment-latest` in Newseye's environment. Targeted method: GRU-TSC from NewsSentiment 1.2.28 (torch 2.0.1+cu118, Python 3.11.17) in its own environment. Both read the same sentence. Scores are P(positive) - P(negative); a threshold t gives positive above t, negative below -t.

## rw: real-world distribution (test, n = 803)

| Method (test) | F1m | F1pn | Accuracy |
|---|---|---|---|
| sentence ±0.15 | 0.662 | 0.679 | 0.666 |
| targeted ±0.15 | 0.803 | 0.809 | 0.809 |
| sentence, tuned ±0.18 | 0.660 | 0.672 | 0.667 |
| targeted, tuned ±0.29 | 0.811 | 0.809 | 0.818 |
| targeted, most likely class | 0.830 | 0.821 | 0.839 |
| combined: blend 1.0 targeted + 0.0 sentence, ±0.29 | 0.811 | 0.809 | 0.818 |
| combined: stacked logistic regression | 0.831 | 0.823 | 0.843 |

Targeted minus sentence, both dev-tuned: F1m +0.150 (95% CI +0.113 to +0.189; targeted not better in 0.0% of 5,000 resamples). Thresholds tuned on dev: sentence ±0.18, targeted ±0.29. Targets the model could not score (sentence tone used): 0.

Combined minus targeted alone (dev-tuned): blend 1.0 targeted + 0.0 sentence F1m +0.000 (95% CI +0.000 to +0.000); stacked logistic regression F1m +0.021 (95% CI +0.001 to +0.040).

Confusion, sentence, tuned ±0.18 (rows gold, columns predicted):

|  | negative | neutral | positive |
|---|---|---|---|
| negative | 234 | 53 | 8 |
| neutral | 98 | 204 | 17 |
| positive | 27 | 64 | 98 |

Confusion, targeted, tuned ±0.29 (rows gold, columns predicted):

|  | negative | neutral | positive |
|---|---|---|---|
| negative | 251 | 31 | 13 |
| neutral | 20 | 262 | 37 |
| positive | 14 | 31 | 144 |

## mt: two or more people per sentence (test, n = 1034)

| Method (test) | F1m | F1pn | Accuracy |
|---|---|---|---|
| sentence ±0.15 | 0.628 | 0.628 | 0.632 |
| targeted ±0.15 | 0.795 | 0.784 | 0.810 |
| sentence, tuned ±0.13 | 0.628 | 0.633 | 0.628 |
| targeted, tuned ±0.34 | 0.826 | 0.809 | 0.843 |
| targeted, most likely class | 0.826 | 0.804 | 0.847 |
| combined: blend 1.0 targeted + 0.0 sentence, ±0.34 | 0.826 | 0.809 | 0.843 |
| combined: stacked logistic regression | 0.831 | 0.810 | 0.849 |

Targeted minus sentence, both dev-tuned: F1m +0.199 (95% CI +0.167 to +0.232; targeted not better in 0.0% of 5,000 resamples). Thresholds tuned on dev: sentence ±0.13, targeted ±0.34. Targets the model could not score (sentence tone used): 0.

Combined minus targeted alone (dev-tuned): blend 1.0 targeted + 0.0 sentence F1m +0.000 (95% CI +0.000 to +0.000); stacked logistic regression F1m +0.004 (95% CI -0.011 to +0.020).

Confusion, sentence, tuned ±0.13 (rows gold, columns predicted):

|  | negative | neutral | positive |
|---|---|---|---|
| negative | 272 | 65 | 9 |
| neutral | 209 | 284 | 38 |
| positive | 23 | 41 | 93 |

Confusion, targeted, tuned ±0.34 (rows gold, columns predicted):

|  | negative | neutral | positive |
|---|---|---|---|
| negative | 290 | 52 | 4 |
| neutral | 42 | 467 | 22 |
| positive | 8 | 34 | 115 |

Sentences whose people have different gold labels: 212 (437 targets). Sentence tone gives every person in a sentence the same class, so it can be right for at most one class per sentence: correct on 202 of 437; targeted correct on 342 of 437.

## Decision

Targeted against sentence - rule met on rw: **yes**; on mt: **yes**. **Switch PERSON mentions to targeted scoring**, threshold ±0.29 (tuned on rw dev).

Combined against targeted alone - blend beats it on both sets: **no**; stacked model: **no**. **Keep the single targeted model**: no combination beats it by more than resampling noise on both test sets.

## Behaviour check: constructed Kenyan sentences

Built to separate the tone of an event from the attitude toward a person; the first four are the annotation guide's worked examples with its labels, the rest follow the same rules. Labels at ±0.15. Not a sample of real text: read it as behaviour, not accuracy. Sentence tone matched 7 of 13, targeted 11 of 13.

| Text | Person | Expected | Sentence | Targeted |
|---|---|---|---|---|
| Ruto condemns the killings in Kisumu. | Ruto | neutral or positive | negative (-0.47) | neutral (+0.07) ✓ |
| Gachagua claims he was sidelined. | Gachagua | negative | negative (-0.35) ✓ | negative (-0.17) ✓ |
| Police tear-gas supporters of Kalonzo. | Kalonzo | neutral | negative (-0.77) | neutral (-0.04) ✓ |
| Raila hits back at critics over IEBC stance. | Raila | neutral | neutral (-0.12) ✓ | negative (-0.18) |
| Kindiki attended the burial of the flood victims in Embu. | Kindiki | neutral | neutral (-0.03) ✓ | positive (+0.17) |
| Seven people died in the crash, Mbadi said. | Mbadi | neutral | negative (-0.75) | neutral (+0.01) ✓ |
| Residents praised Murkomen for restoring calm in Kerio Valley. | Murkomen | positive | positive (+0.81) ✓ | positive (+0.96) ✓ |
| Critics accused Murkomen of failing to stop the attacks in Kerio Valley. | Murkomen | negative | negative (-0.78) ✓ | negative (-0.99) ✓ |
| Murkomen visited Kerio Valley on Tuesday. | Murkomen | neutral | neutral (+0.02) ✓ | neutral (+0.02) ✓ |
| Kalonzo praised Karua for her courage but accused Ruto of betraying voters. | Karua | positive | negative (-0.33) | positive (+0.47) ✓ |
| Kalonzo praised Karua for her courage but accused Ruto of betraying voters. | Ruto | negative | negative (-0.33) ✓ | negative (-0.98) ✓ |
| Wetangula thanked Sakaja for his support, while Babu Owino was booed off the stage. | Sakaja | positive | neutral (+0.04) | positive (+0.62) ✓ |
| Wetangula thanked Sakaja for his support, while Babu Owino was booed off the stage. | Babu Owino | negative | neutral (+0.04) | negative (-0.90) ✓ |

## Caveats

- GRU-TSC was trained on NewsMTSC's train split: this test is in-domain for it and out-of-domain for the sentence model, which was trained on tweets. That is the practical choice Newseye faces between two existing tools, but it inflates the gap relative to Kenyan text.
- NewsMTSC is US political news. Kenyan headlines, Sheng and Swahili, and local context are outside it; the labelled Kenyan sample (`eval/framing`, two annotators) is the test that answers that.
- NewsMTSC discarded sentences under 50 characters, so headlines are outside its training data.
