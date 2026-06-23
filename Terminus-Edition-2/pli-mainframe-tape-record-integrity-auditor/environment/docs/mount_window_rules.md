# Mount Window Rules

When `WINDOW_MODE` is `ON`, the harness loads `/app/config/mount_windows.psv`.

Timestamps are 14-digit UTC strings (`YYYYMMDDHHMMSS`). Both catalog `recv_ts` and audit `audit_ts` must be numeric.

For a qualifying catalog row and audit pair on the same `volume_id`:
- Window `state` must equal `OPEN_MOUNT_STATE` from `/app/src/tape_rules.pli` (case-insensitive).
- `open_ts <= recv_ts <= close_ts`
- `recv_ts <= audit_ts <= close_ts`

Closed, missing, malformed, or unlisted windows reject the match.

When multiple unused catalog rows qualify, choose the latest `recv_ts`. When timestamps tie, choose the earliest catalog data row by zero-indexed position in `/app/data/tape_catalog.psv` (first data row after the header is index 0).
