# Milestone 1: Block API readiness until dependencies are healthy

You are on call for `docker-compose-cache-backed-api-recovery`. Repair `/app/tools/compose_api_recovery.py` using `/app/docs/simulator_contract.md`, `/app/docs/operator_runbook.md`, and incident evidence under `/app/docs`.

## Symptom

The `up` subcommand marks `services.api` as `healthy` even when `services.db` or `services.cache` is not `healthy` (for example `created` or `stopped`).

## Required behavior

1. Run `python3 /app/tools/compose_api_recovery.py up --state <state.json> --out <outdir>`.
2. When either dependency is not exactly `healthy`, persist `services.api = blocked`, write `<outdir>/result.json` with `status: BLOCKED` and a `reason` containing the word `dependency`, and exit non-zero.
3. When both dependencies are `healthy`, set `services.api = healthy`, write `result.json` with `status: UP`, and exit zero.
4. Malformed state (missing `services`, wrong types) must fail closed: `result.json` status `FAILED_CLOSED`, non-zero exit, no partial mutation.

## Partial state files (important)

Tests pass **minimal** state JSON with only `services`, `db`, `cache`, and
`outbox`. Optional keys (`processed_requests`, `schema_version`, `app_version`,
`migration_lock`) may be omitted — apply the defaults from
`/app/docs/simulator_contract.md` and continue. Do **not** return
`FAILED_CLOSED` just because those optional keys are absent.

Example valid input for milestone 1:

```json
{
  "services": {"db": "healthy", "cache": "created", "api": "stopped"},
  "db": {},
  "cache": {},
  "outbox": []
}
```

Do not add shortcut unlock strings, replace the tool with static fixtures, or edit tests.
