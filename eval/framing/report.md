# Framing on Newseye's corpus: sentence tone against targeted sentiment

Run 2026-11-06 11:49 from `eval/framing`. Gold labels: two annotators, disagreements settled together. Thresholds tuned on the dev split; everything below is on test.

Agreement: Cohen's kappa 0.752 on 215 independently labelled items (three classes); 0.730 quadratic-weighted on the 7-point scale.

Items with a gold class: dev 72, test 172. Test gold: negative 31, neutral 107, positive 34.

| Method | F1m | F1pn | Accuracy |
|---|---|---|---|
| sentence ±0.15 | 0.579 | 0.562 | 0.587 |
| targeted ±0.15 | 0.699 | 0.666 | 0.715 |
| sentence, tuned ±0.48 | 0.556 | 0.442 | 0.680 |
| targeted, tuned ±0.11 | 0.698 | 0.675 | 0.703 |
| targeted, most likely class | 0.698 | 0.636 | 0.756 |

Targeted minus sentence, both at ±0.15: F1m +0.120 (95% CI +0.031 to +0.209; not better in 0.4% of resamples).

Targeted minus sentence, both dev-tuned: F1m +0.142 (95% CI +0.042 to +0.248; not better in 0.4% of resamples).

Targeted minus sentence, targeted's own class against sentence ±0.15: F1m +0.119 (95% CI +0.025 to +0.215; not better in 0.8% of resamples).

## People only (test)

97 people: negative 25, neutral 49, positive 23. Tuned on 40 dev people: negative 4, neutral 22, positive 14.

| Thresholds | Targeted F1m | Sentence F1m | Targeted minus sentence |
|---|---|---|---|
| thresholds tuned on the dev split's people (targeted ±0.15, sentence ±0.25) | 0.719 (0.626 to 0.801) | 0.613 (0.506 to 0.715) | +0.105 (-0.023 to +0.231) |
| the site's thresholds (targeted ±0.29, sentence ±0.15) | 0.699 (0.602 to 0.788) | 0.670 (0.569 to 0.760) | +0.029 (-0.082 to +0.151) |

Confusion, targeted at the site's threshold (rows gold, columns predicted):

|  | negative | neutral | positive |
|---|---|---|---|
| negative | 16 | 6 | 3 |
| neutral | 2 | 33 | 14 |
| positive | 1 | 3 | 19 |

## Subsets (test)

F1m per subset; under 20 items is too few to read anything into.

| Subset | n | sentence ±0.15 | targeted ±0.15 | sentence, tuned ±0.48 | targeted, tuned ±0.11 | targeted, most likely class |
|---|---|---|---|---|---|---|
| field: body | 24 | 0.330 | 0.431 | 0.399 | 0.431 | 0.376 |
| field: headline | 72 | 0.631 | 0.832 | 0.519 | 0.815 | 0.743 |
| field: snippet | 76 | 0.604 | 0.662 | 0.607 | 0.669 | 0.719 |
| gold: agreed | 146 | 0.628 | 0.707 | 0.566 | 0.698 | 0.738 |
| gold: settled | 26 | 0.320 | 0.604 | 0.507 | 0.647 | 0.454 |
| names one entity | 43 | 0.583 | 0.768 | 0.619 | 0.731 | 0.791 |
| names several | 129 | 0.565 | 0.665 | 0.520 | 0.675 | 0.653 |
| type: PERSON | 97 | 0.670 | 0.719 | 0.589 | 0.704 | 0.741 |
| type: not PERSON | 75 | 0.431 | 0.600 | 0.475 | 0.628 | 0.474 |

Confusion, sentence, tuned ±0.48 (rows gold, columns predicted):

|  | negative | neutral | positive |
|---|---|---|---|
| negative | 12 | 18 | 1 |
| neutral | 9 | 94 | 4 |
| positive | 2 | 21 | 11 |

Confusion, targeted, tuned ±0.11 (rows gold, columns predicted):

|  | negative | neutral | positive |
|---|---|---|---|
| negative | 23 | 5 | 3 |
| neutral | 6 | 67 | 34 |
| positive | 2 | 1 | 31 |

## Errors

51 test items the tuned targeted method got wrong are in `errors.csv`. Causes recorded so far: context 31, gold-wrong 6, weak 5, headline-grammar 5, target-confusion 4. Categories: weak, both-valid, target-confusion, context, gold-wrong, headline-grammar, kenyan-context, none (README, section 6).

Thresholds tuned on dev: sentence ±0.48, targeted ±0.11.
