# Rollup Window Rules

When `WINDOW_MODE` is `ON`, the harness loads `/app/config/rollup_windows.psv`.

Timestamps are 14-digit UTC strings (`YYYYMMDDHHMMSS`). Both directive `ingest_ts` and accumulator `rollup_ts` must be numeric.

For a qualifying directive row and accumulator pair on the same `stream_id`:
- Window `state` must equal `OPEN_ROLLUP_STATE` from `/app/src/rollup_rules.pli` (case-insensitive).
- `open_ts <= ingest_ts <= close_ts`
- `ingest_ts <= rollup_ts <= close_ts`

Closed, missing, malformed, or unlisted windows reject the match.

When multiple unused directive rows qualify, choose the latest `ingest_ts`. When timestamps tie, choose the earliest directive data row by zero-indexed position in `/app/data/directives.psv`.
