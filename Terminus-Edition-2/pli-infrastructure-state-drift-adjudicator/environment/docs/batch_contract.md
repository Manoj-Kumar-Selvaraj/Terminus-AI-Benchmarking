# Batch Contract

Agent-editable surface is limited to `/app/src/drift_rules.pli` and `/app/src/drift_batch.pli`.

- **Rules deck** — eligible state, open audit state, allowed `scan_code` values, and `ALIAS_*` maps.
- **Batch deck** — `%SET` switches: `KEY_COMPARE`, `CONSUME`, `ALIAS_MODE`, `WINDOW_MODE`.

The gawk harness under `/app/scripts/` is fixed. Do not patch it to pass tests.

Outputs must match `/app/docs/operations.md`.
