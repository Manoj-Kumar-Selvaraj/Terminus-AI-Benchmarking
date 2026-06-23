Rollup windows, weighted control totals, downstream delivery, and control-held group downgrades are disabled or incomplete. Extend the PL/I control deck so `/app/scripts/run_batch.sh` enforces stream-scoped windows, reconciles weighted groups, publishes downstream files, and downgrades report rows in `CONTROL_HELD` groups to `SKIPPED` with blank `segment_id`.

Preserve all milestone 1 behavior: full-key matching with alias canonicalization, signed opcode direction, validation, consumption, and deterministic ingest selection.

Open rollup windows require both directive `ingest_ts` and accumulator `rollup_ts` inside the same stream's open window with valid non-reversed 14-digit timestamps. Weighted controls read active radix weights and reconcile group counts and weighted cents against control totals with tolerance. Write `/app/out/rollup_controls.psv` using the schema documented in `/app/docs/rollup_control_totals.md`: `stream_id|base_radix|segment_id|actual_count|actual_weighted_cents|expected_count|expected_weighted_cents|tolerance_cents|status`. When a group is `CONTROL_HELD`, matching rows in the main report must be downgraded even if they initially rolled.

Downstream delivery writes `/app/out/downstream/accepted_rollups.psv`, `/app/out/downstream/rejected_rollups.psv`, and `/app/out/downstream/manifest.json` per `/app/docs/downstream_delivery_contract.md`. Accepted output includes only `CONTROL_OK` groups whose netting (when present) is satisfied.

Ignore ledger replay, settlement cutoff, capacity limits, directive holds, restart commits, and sequence netting for this repair.
