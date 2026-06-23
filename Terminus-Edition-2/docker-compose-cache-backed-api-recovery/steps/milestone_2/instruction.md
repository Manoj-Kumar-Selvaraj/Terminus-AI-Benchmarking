# Milestone 2: Namespace cache by tenant and schema provenance

Continue repairing `/app/tools/compose_api_recovery.py`. Milestone 1 dependency gating must keep working.

## Symptom

Cache reads and writes use bare logical keys, so tenants collide and stale values survive `PUT` operations.

## Required behavior

1. `request --method GET` and `PUT` must use cache keys:
   `{tenant}|schema{schema_version}|{app_version}|{logical_key}`
   (example: `a|schema2|v2|k`). Include the resolved `cache_key` in `result.json`.
2. After a successful `PUT`, invalidate existing cache entries for that tenant/logical key (entries ending with `|{key}`, equal to the bare logical key, or matching the tenant namespace prefix) before appending the outbox record.
3. Preserve milestone 1 `up` dependency gating and `result.json` conventions. Re-run `up` with an unhealthy dependency and confirm the API stays `blocked`.

See `/app/docs/simulator_contract.md` for the full state schema and CLI flags.
