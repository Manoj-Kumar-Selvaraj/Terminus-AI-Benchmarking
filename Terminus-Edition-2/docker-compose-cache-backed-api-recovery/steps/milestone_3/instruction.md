# Milestone 3: Replay restart outbox idempotently

Continue repairing `/app/tools/compose_api_recovery.py`. Milestones 1–2 behavior must remain intact.

## Symptom

Duplicate `request_id` values create duplicate outbox rows and side effects. `restart` does not deduplicate the outbox, does not clear stale cache entries, and can leave the API healthy when dependencies are down.

## Required behavior

1. `request --request-id <id>`: if the ID is already in `processed_requests`, return `DUPLICATE` without duplicating outbox entries or changing `db` rows; otherwise record the ID after a successful write.
2. `restart --state <state> --out <out>`: deduplicate `outbox` by `request_id` (keep one row per ID), delete cache keys referenced by each unique outbox entry, then re-run the milestone 1 dependency gate before setting `services.api` (API must become `blocked` when `services.cache` or `services.db` is not exactly `healthy`).
3. Write `result.json` under `--out` for every subcommand.

Contract details: `/app/docs/simulator_contract.md`.
