# Milestone 4: Guard schema migrations with locks and compatibility

Continue repairing `/app/tools/compose_api_recovery.py`. Milestones 1–3 must keep passing.

## Symptom

`migrate` advances `schema_version` even when another holder owns `migration_lock`, or when `--app-version` is incompatible with the target schema.

## Required behavior

1. `migrate --target-schema <n> --holder <name> --app-version <ver>`:
   - Fail closed (non-zero, `FAILED_CLOSED`, unchanged `schema_version`) if `migration_lock` is set to a different holder.
   - For target schema 2+, reject `--app-version` values outside `v2` and `v3`.
   - On success, set `schema_version`, release `migration_lock` to `null`, and return `MIGRATED`.
2. Preserve request/restart/up semantics from earlier milestones.

See `/app/docs/simulator_contract.md`.
