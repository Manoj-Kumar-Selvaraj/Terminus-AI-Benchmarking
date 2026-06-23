# Batch Contract

Agent-editable surface is limited to `/app/src/semantic_rules.pli` and `/app/src/semantic_batch.pli`.

- **Rules deck** — `DCL` constants: eligible state, open window state, allowed `mode_code` values, and `ALIAS_*` maps.
- **Batch deck** — `%SET` switches read by the harness: `KEY_COMPARE`, `CONSUME`, `ALIAS_MODE`, `WINDOW_MODE`.

The gawk harness under `/app/scripts/` is fixed. Do not patch it to pass tests.

Outputs must land in `/app/out/` with the column order documented in `/app/docs/operations.md`.
