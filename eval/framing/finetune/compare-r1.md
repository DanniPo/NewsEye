# Fine-tuned GRU-TSC against the published weights: run r1

Tuned weights: `C:\Users\HP\Projects\Newseye\eval\framing\finetune\experiments\r1\state_dict\grutsc_kenya_val_f1_macro_0.7987_epoch1`, from `grutsc_v1-0-0`, 3 epochs, learning rate 2e-05, batch 4, seed 20261023. Worker: NewsSentiment 1.2.28, torch 2.0.1+cu118.

**Decision rule.** Use the tuned weights if, on the PERSON items of the Kenyan test split, their F1m at a threshold tuned on the Kenyan dev split is higher than the published weights' at theirs, the paired 95% bootstrap interval of the difference lies wholly above zero, and on neither NewsMTSC test set (rw, mt) does their F1m (the model's own class) fall more than 0.03 below the published weights'. Otherwise the published weights stay.

**Verdict.** Keep the published weights: the Kenyan gain is not clear of resampling noise; F1m on NewsMTSC rw fell by 0.042; F1m on NewsMTSC mt fell by 0.038.

## Kenyan evaluation sample, PERSON items

Labels from gold.csv. Thresholds tuned on 40 dev items; scored on 97 test items (negative 25, neutral 49, positive 23).

| Weights | Threshold (dev) | F1m | F1pn | Accuracy | F1m, own class |
|---|---|---|---|---|---|
| published | ±0.17 | 0.709 | 0.714 | 0.701 | 0.741 |
| tuned | ±0.79 | 0.662 | 0.628 | 0.680 | 0.694 |

Difference in F1m (tuned − published): -0.047, 95% interval -0.153 to +0.055; tuned not better in 81.8% of 5,000 resamples.

Confusion on test (rows gold, columns predicted: negative, neutral, positive):

- published:  18   4   3 /   2  29  18 /   1   1  21
- tuned:  11   9   5 /   0  35  14 /   0   3  20

## What the tuning forgot: NewsMTSC test sets

F1m of the model's own class, as the NewsMTSC paper reports it.

| Test set | Items | Published | Tuned | Change |
|---|---|---|---|---|
| rw | 803 | 0.830 | 0.789 | -0.042 |
| mt | 1034 | 0.826 | 0.788 | -0.038 |

## The tuned weights file

Deleted on 9 November 2026 to free 584 MB: the verdict kept the published
weights, and nothing loads the tuned ones (`NEWSMTSC_STATE_DICT` is unset). The
run's record stays in `experiments/r1/`: `train.log`, the per-epoch
`statistics/`, `experiment_results.jsonl` and the training, dev and test text in
`datasets/kenya/`. To have tuned weights again, build and train a new run from
the same labelled sheet (`python -m backend.eval.finetune_framing build --run r2`,
then `train --run r2`): the defaults are r1's settings and seed, and training
into r1 itself would overwrite its log. Training on a graphics card is not
exactly repeatable, so the scores may differ slightly from those above.
