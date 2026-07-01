# Offline DB2 simulator contract

`/app/internal/db2sim` is the trusted local DB2-style simulator. It stores all tables in a JSON state file supplied by `--db`.

Modeled SQLCODEs:

- `0`: statement succeeded and may be committed.
- `+100`: no master row was found. This is a business reject, not a job ABEND.
- `-911`: lock timeout/deadlock. This is retryable; do not turn it into a reject or advance beyond the locked sequence.
- `-803`: duplicate applied event marker. Reruns must not duplicate committed side effects.
- `-530`: referential/business constraint failure. Credit-limit changes must fail atomically when this occurs.

Compatibility constraints:

- Keep `/app/bin/run_finbulk.sh` and its flags: `--batch`, `--input`, `--db`, `--out`, `--abend-after`, and optional `--control PATH`.
- Keep JSON table names: `master`, `risk`, `ledger`, `audit`, `rejects`, `pending_locks`, `checkpoint`, `applied_events`, and `control_totals`.
- Keep the fixed-width input and reject-output formats documented in `/app/docs/fixed_width_layout.md`.
- Simulated ABEND via `--abend-after` returns process status `66` after writing summary and checkpoint state.
- Retryable lock contention returns process status `75` with pending-lock evidence.
- Output files are `summary_<batch>.json`, `rejects_<batch>.dat`, and `pending_locks_<batch>.json` beneath `--out`. All three files are written on every exit path, including pre-mutation `FAILED_CLOSED` aborts, with empty reject and pending-lock files when there are no rows.
- `pending_locks_<batch>.json` is a bare JSON array, not an object wrapper. Each pending lock record must include `account`, integer `sqlcode`, and `lock_holder`; additional record context such as batch or sequence may be included.
- Summary status literals are `OK`, `FAILED_CLOSED`, `SIMULATED_ABEND`, and `RETRYABLE_LOCK`. Lock summaries include integer `pending_locks`.
- `summary_<batch>.json` must include `batch_id`, integer `applied`, integer `rejected`, integer `skipped`, and `status` on every exit path. `RETRYABLE_LOCK` summaries must also include integer `pending_locks`. `FAILED_CLOSED` summaries may include an `error` string describing the failed gate.
- Do not replace the workflow with precomputed output files. The verifier runs generated batches and inspects the DB state.

## Settlement control manifest (milestone 5)

When `--control PATH` is supplied, the manifest JSON must contain:

- `batch_id`
- `business_date`
- `source`
- `expected_detail_count`
- `expected_financial_total`

Successful controlled runs persist `control_totals[batch_id]` with:

- `status` (`SETTLED` on success)
- `detail_count`
- `financial_total`
- `input_sha256`
- the identifying control fields above

Same batch id with a different input hash must write summary status `FAILED_CLOSED`; same payload reruns remain idempotent.

## Settlement chain and close ceremony (milestone 6)

Successful controlled runs also persist tamper-evident chain provenance on the same `control_totals[batch_id]` entry:

- `prior_chain_sha256`: the previous settled batch's `chain_sha256` for the same `business_date`, or 64 ASCII zeros (`"0"*64`) if this is the first settled batch for that date.
- `chain_sha256`: lowercase hex `sha256(prior_chain_sha256 || batch_id || input_sha256 || business_date)`, where the four parts are concatenated as UTF-8 bytes in that exact order with no separator.
- `prior_batch_id`: the immediately preceding settled batch id for the same business date, or `null` (or omitted) if this is the first.

The simulator state also maintains `chain_index[business_date]` as an ordered JSON array of settled batch ids for that date. New settlements append to the array. Same-payload idempotent reruns do **not** append a duplicate entry and do **not** mutate any chain field.

An optional control manifest field `prior_batch_id` declares the expected chain tip:

- When present, it must equal the current tip of `chain_index[business_date]` and the chain must verify against the named prior settlement. A mismatch fails closed with summary status `FAILED_CLOSED` and `error` containing `UNMET_DEPENDENCY`. No simulator state changes.
- When absent, the run inherits the current chain tip without an explicit assertion; legacy controlled invocations remain compatible.

Close mode runs with `--close DATE` instead of `--input/--batch`:

- Walks `chain_index[DATE]` in order, recomputes each link from stored `control_totals` entries, and verifies the stored `chain_sha256` matches the recomputed value byte for byte.
- On success writes `close_<DATE>.json` with `status` `CLOSED`, `business_date`, `batch_count`, `chain_root` (the final link's `chain_sha256`, or 64 zeros for an empty date), and a `batches` array of `{batch_id, chain_sha256, detail_count, financial_total}` in order. Also writes `glfeed_<DATE>.dat` (see `fixed_width_layout.md`). Exit code `0`.
- On chain breakage writes `close_<DATE>.json` with `status` `CLOSE_BROKEN`, an `error` string identifying the first broken link, an empty `batches` array, and an empty `glfeed_<DATE>.dat`. Exit code is nonzero.
- A close mode invocation does **not** acquire a per-batch lock and does **not** mutate `master`, `risk`, `ledger`, `audit`, `checkpoint`, `applied_events`, `rejects`, `pending_locks`, or `control_totals`.

Per-batch process fencing applies to every mutating run (any invocation with `--input`):

- The runner must acquire an exclusive non-blocking advisory lock (`flock(LOCK_EX|LOCK_NB)`) on `<dirname(db)>/.lock_<batch_id>` before reading or mutating simulator state.
- If the lock cannot be acquired, the run exits with process status `73`, writes summary status `BATCH_BUSY`, and writes the standard three output files (`summary_<batch>.json`, `rejects_<batch>.dat`, `pending_locks_<batch>.json`) with empty reject and pending-lock contents and no DB mutation.
- Different batch ids may run concurrently. A lock file left behind by a crashed prior holder is reusable because OS-level flock is released on process death.

Mid-LIM abend uses a dedicated flag `--abend-after-lim-master`:

- When present, the runner processes details normally until the next `LIM` detail; after the master credit-limit half commits but before the risk exposure half commits, the runner rolls the in-process LIM back so neither half is durably applied, writes summary status `SIMULATED_ABEND`, and exits with status `66`.
- The durable simulator state must show neither half applied and no applied-event marker for the aborted LIM detail. A subsequent run without the flag must commit that LIM exactly once across both tables.
- The flag is mutually exclusive with `--abend-after N` taking effect on the same detail; if both apply to the same LIM, the mid-LIM behavior wins.
