# Pass Window Rules

When `WINDOW_MODE` is `ON`, the harness loads `/app/config/pass_windows.psv`.

Timestamps are 14-digit UTC strings (`YYYYMMDDHHMMSS`). Both catalog `recv_ts` and audit `audit_ts` must be numeric.

For a qualifying catalog row and audit pair on the same `craft_id`:
- Window `state` must equal `OPEN_PASS_STATE` from `/app/src/audit_rules.pli` (case-insensitive).
- `open_ts <= recv_ts <= close_ts`
- `recv_ts <= audit_ts <= close_ts`

Closed, missing, malformed, or unlisted windows reject the match.

When multiple unused catalog rows qualify, choose the latest `recv_ts`. When timestamps tie, choose the earliest catalog data row by zero-indexed position in `/app/data/catalog.psv`.
