# Batch Contract

Agent-editable surface is limited to `/app/src/manifest_rules.pli` and `/app/src/manifest_batch.pli`.

- **Rules deck** — eligible state, open rollout state, allowed `check_code` values, and `ALIAS_*` maps.
- **Batch deck** — `%SET` switches: `KEY_COMPARE`, `CONSUME`, `ALIAS_MODE`, `WINDOW_MODE`.

The gawk harness under `/app/scripts/` is fixed. Do not patch it to pass tests.

Outputs must match `/app/docs/operations.md`.
