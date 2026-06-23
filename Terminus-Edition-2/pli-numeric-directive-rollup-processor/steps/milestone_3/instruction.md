Committed rollup evidence and settlement cutoff enforcement are missing. Extend the PL/I control deck so `/app/scripts/run_batch.sh` replays committed ledger rows safely and rejects rollups outside the business-day cutoff calendar.

Preserve all milestone 1 and milestone 2 behavior.

When ledger mode is on, load `/app/state/rollup_ledger.psv` and treat rows with status `COMMITTED` as replay duplicates: emit `SKIPPED` with `REPLAY_DUPLICATE` in `/app/out/rollup_exceptions.csv` and do not consume a fresh directive. The exceptions file is pipe-delimited with columns `claim_id|line_id|stream_id|reason|detail`; `reason` contains values such as `REPLAY_DUPLICATE` and `detail` carries the matched exception context. Append newly committed rows to `/app/out/rollup_ledger.psv`.

Read `/app/state/restart_checkpoint.txt` and write `/app/out/restart_audit.txt` with `checkpoint_status` (`OK`, `MISSING`, `STALE`, or `AHEAD`) and `committed_rows` for this run. Checkpoint anomalies must not suppress valid non-replay processing.

Cutoff mode derives the business date from directive `ingest_ts` (first eight digits). On `OPEN` calendar days both `ingest_ts` and `rollup_ts` must be less than or equal to the calendar `cutoff_ts`.

Ignore capacity limits, directive holds, restart group commits, and sequence netting for this repair.
