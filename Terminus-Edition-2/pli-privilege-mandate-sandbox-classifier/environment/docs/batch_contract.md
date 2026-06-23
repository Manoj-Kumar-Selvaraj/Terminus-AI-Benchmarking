# Batch Contract

Agent-editable surface is limited to `/app/src/mandate_rules.pli` and `/app/src/mandate_batch.pli`.

- **Rules deck** — eligible state, open sandbox state, allowed `verdict_code` values, and `ALIAS_*` maps.
- **Batch deck** — `%SET` switches: `KEY_COMPARE`, `CONSUME`, `ALIAS_MODE`, `WINDOW_MODE`.

The gawk harness under `/app/scripts/` is fixed. Do not patch it to pass tests.

Outputs must match `/app/docs/operations.md`.
