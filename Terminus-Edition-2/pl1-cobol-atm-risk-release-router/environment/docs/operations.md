# Operations handoff

Run the batch with `/app/scripts/run_batch.sh`. The starter program intentionally leaves several production defects in the ATM release flow. Operators have reported that simple hold/release matching is no longer enough: releases must preserve card-level exposure state, terminal trust controls, review queues, and restart-safe commit journals.

The PL/I-style files under `/app/src` and `/app/config` are configuration decks. The shell harness and pipe-delimited data contracts are fixed interfaces. Do not replace the task by writing expected output files directly.
