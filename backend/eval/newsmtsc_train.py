"""NewsSentiment's trainer, continuing from the whole published GRU-TSC model.

NewsSentiment's own trainer (python -m NewsSentiment.train) loads --state_dict
and then, as training starts, re-initialises every layer outside the language
model: GRU-TSC's knowledge-source projection, its GRU and its classifier. Fine-
tuning would keep the published RoBERTa but start the rest from random, so the
first steps undo what the head had learnt from NewsMTSC. This runs the same
trainer with that reset switched off whenever starting weights are given.

Run under NEWSMTSC_PYTHON, like tsc_worker.py, and imports nothing from
Newseye; every argument goes to the trainer unchanged. finetune_framing.py
train starts it:

    <NEWSMTSC_PYTHON> -I backend/eval/newsmtsc_train.py --own_model_name grutsc \\
        --dataset_name kenya --experiment_path <run> --state_dict <weights> ...
"""
import sys

from NewsSentiment import train


def keep_loaded_weights(instructor):
    train.logger.info("keeping the weights loaded from %s", instructor.opt.state_dict)


def main():
    opt = train.parse_arguments()
    if opt.state_dict:
        train.Instructor._reset_params_of_own_model = keep_loaded_weights
    train.logger.info("python bin: %s", sys.executable)
    train.prepare_and_start_instructor(opt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
