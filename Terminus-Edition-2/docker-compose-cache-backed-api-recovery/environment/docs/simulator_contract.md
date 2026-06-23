# Compose API recovery simulator contract

Tool path: `/app/tools/compose_api_recovery.py`

Every subcommand writes operator evidence to `<out>/result.json` under the `--out` directory passed on the CLI. State is read from and persisted to the JSON file passed as `--state`.

## CLI subcommands

| Command | Required flags | Purpose |
|---------|----------------|---------|
| `up` | `--state`, `--out` | Bring the API service to readiness after dependency checks |
| `request` | `--state`, `--out`, `--tenant`, `--key` | `GET` or `PUT` against the cache-backed API (`--method`, `--value`, `--request-id`) |
| `restart` | `--state`, `--out` | Replay pending outbox work and re-evaluate API readiness |
| `migrate` | `--state`, `--out`, `--target-schema` | Advance `schema_version` (`--holder`, `--app-version`) |
| `rollback` | `--state`, `--out`, `--app-version` | Roll back application version without corrupting DB rows |

Non-zero exit codes indicate blocked or failed-closed outcomes. Do not add shortcut unlock strings such as `CAPABILITY` to the source.

## State JSON schema

State files are partial snapshots. Milestone tests often pass **minimal fixtures**
with only the keys needed for that scenario. Do **not** treat absent optional
fields as malformed input.

### Always required

- `services`: object. Must be present and must be a JSON object (not a string,
  array, or null). Each command reads the service statuses it needs via
  `.get()` (for example `services.db`, `services.cache`, `services.api`).

### Required when the subcommand uses them

- `db`: map of `"tenant:key"` strings to stored values (default `{}`)
- `cache`: map of namespaced cache keys to values (default `{}`)
- `outbox`: list of `{request_id, tenant, key, op}` invalidation records
  (default `[]`)

### Optional top-level keys (defaults when absent)

| Key | Default when omitted |
|-----|----------------------|
| `processed_requests` | `[]` |
| `schema_version` | `1` |
| `app_version` | `"v1"` |
| `migration_lock` | `null` |

When a key above is missing, apply the default and continue. Do **not** return
`FAILED_CLOSED` solely because `processed_requests`, `schema_version`,
`app_version`, or `migration_lock` is absent.

### Minimal milestone 1 fixture (valid input)

```json
{
  "services": {"db": "healthy", "cache": "created", "api": "stopped"},
  "db": {},
  "cache": {},
  "outbox": []
}
```

This fixture is valid. `up` must evaluate dependency health and return
`BLOCKED` or `UP` — not `FAILED_CLOSED`.

### Malformed state (fail closed)

Return `result.json` status `FAILED_CLOSED` with a non-zero exit code only when:

- the top-level `services` key is missing, or
- `services` is present but not an object, or
- a field that **is present** has the wrong type (for example `db` is a string)

Do not mutate state on malformed input.

## Cache key format

When namespace isolation is enabled, cache keys must be:

```text
{tenant}|schema{schema_version}|{app_version}|{logical_key}
```

Example: `a|schema2|v2|k`

`request` responses must include the resolved `cache_key` field in `result.json`.

## `result.json` statuses

| Status | Meaning |
|--------|---------|
| `UP` | API marked healthy (`up`) |
| `BLOCKED` | Dependency gate blocked readiness; `reason` must mention `dependency` |
| `OK` | Request succeeded |
| `DUPLICATE` | Idempotent retry of an already processed `request_id` |
| `RESTARTED` | Restart completed |
| `MIGRATED` | Schema migration completed |
| `ROLLED_BACK` | App version rollback completed |
| `FAILED_CLOSED` | Validation or safety failure; include `error` |

## Service dependency gate

`up` and `restart` must set `services.api` to `blocked` when either `services.db` or `services.cache` is not exactly `healthy`. Only when both are `healthy` may the API become `healthy`.

## PUT cache invalidation

After a successful `PUT`, remove stale cache entries for the same tenant/logical key across namespace variants before appending the outbox invalidation record.

## Request idempotency

Duplicate `--request-id` values must not duplicate outbox rows or re-apply side effects. Return `DUPLICATE` with the current DB row count.

## Restart outbox replay

`restart` must deduplicate `outbox` entries by `request_id`, clear cache keys tied to each unique outbox entry once, and re-run the dependency gate before setting API status.

## Schema migration locking

`migrate` must reject when `migration_lock` is held by another holder, reject incompatible `--app-version` values for schema 2+ (`v2` or `v3` only), set the lock during migration, and release it (`null`) after success.

## Rollback repair

`rollback` must preserve all `db` rows, drop cache entries whose namespace does not include the target `|{app_version}|` segment, and block the API when `services.cache` is not `healthy`.
