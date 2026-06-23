# Milestone 5: Rollback app version without corrupting DB or cache

Finalize `/app/tools/compose_api_recovery.py`. All prior milestone behavior must remain correct.

## Symptom

`rollback` changes `app_version` but leaves incompatible cache namespaces in place and can mark the API healthy while `services.cache` is unhealthy.

## Required behavior

1. `rollback --app-version <ver>` must preserve every `db` row.
2. Remove cache entries whose key does **not** contain the literal segment `|{app_version}|` for the rollback target (example: rolling back to `v1` keeps `a|schema2|v1|k` and removes `a|schema2|v2|k`).
3. After rollback, set `services.api` to `blocked` when `services.cache` is not exactly `healthy`; otherwise leave API status unchanged.
4. Write `result.json` with `ROLLED_BACK`, `app_version`, `db_count`, and `cache_count`.

Full CLI and schema reference: `/app/docs/simulator_contract.md`.
