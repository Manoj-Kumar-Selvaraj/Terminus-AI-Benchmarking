Continue running the FNOL reserve batch through `/app/scripts/run_batch.sh` and preserve every milestone 1 rule documented in `/app/docs/operations.md`.

Milestone 2 adds realtime window gating from `/app/config/windows.psv` with pipe-delimited columns `loss_unit|open_ts|close_ts|state`. Timestamps must be exactly 14-digit numeric UTC strings; malformed timestamps cause the adjustment to be `UNMATCHED`. Only windows whose `state` equals runtime `OPEN_WINDOW_STATUS` (case-insensitive) are eligible.

The claim `fnol_ts` must fall inside the open window (`open_ts <= fnol_ts <= close_ts`). The adjustment `adjust_ts` must be on or after the claim `fnol_ts` and not after `close_ts`. When multiple unused claim rows qualify, choose the latest `fnol_ts`; if timestamps tie, choose the earliest claim input row.

Closed windows (any `state` other than `OPEN_WINDOW_STATUS`) reject matching. Keep all milestone 1 outputs and schemas unchanged.
