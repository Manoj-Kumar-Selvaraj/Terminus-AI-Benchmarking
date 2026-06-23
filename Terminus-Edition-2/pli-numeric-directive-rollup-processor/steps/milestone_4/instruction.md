Stream capacity limits, directive holds, and ABEND-safe group commits are not enforced. Extend the PL/I control deck so `/app/scripts/run_batch.sh` applies cumulative capacity by stream and canonical radix, quarantines held claims before matching, and appends control-OK group commits without double-committing on reruns.

Preserve all prior milestone behavior.

Capacity mode tracks cumulative absolute rolled cents per `stream_id|canonical_base_radix` in accumulator order. Overflow produces `SKIPPED` rows, does not consume directives, and emits `CAPACITY_HOLD` exceptions. Hold mode quarantines accumulators whose `claim_id` appears in `/app/config/directive_holds.psv` before matching.

Restart mode loads `/app/state/rollup_commits.psv`, appends one commit row per newly finalized `CONTROL_OK` group to `/app/out/rollup_commits.psv`, and skips groups already present. Write `/app/out/capacity_position.txt` as pipe-delimited rows with header `stream_id|base_radix|limit_cents|used_cents|remaining_cents`, reporting limit, used, and remaining cents per capacity key.

Ignore sequence locks and cross-claim netting for this repair.
