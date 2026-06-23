This is a three-milestone Go task. Repair the streaming usage credit reconciler in `/app/cmd/reconcile/main.go` so `/app/data/credits.csv` matches against `/app/data/playbacks.csv` with region cutoff rules from `/app/config/region_cutoffs.csv`. Milestone 1 establishes the full matching contract, report schema, and summary keys. Later milestones add explicit alias documentation and harder cutoff or tie-break scenarios. Keep the deliverable as a Go CLI: the verifier compiles with `/usr/local/go/bin/go` and runs the produced binary.

Fix the reconciler for milestone 1. A credit matches a playback row only when all of the following hold:

- `stream_id`, `account_id`, `region`, and `minutes` are equal on both rows (full string equality for `stream_id`, not a prefix match).
- The playback `status` is exactly `POSTED`.
- The credit `reason` is one of `BUFFER`, `DUPLICATE`, or `OUTAGE` (see `/app/config/reasons.csv`).
- The credit `device` matches the playback `device` after normalizing legacy aliases from `/app/config/device_aliases.csv`: `TV` to `CTV`, `PHONE` to `MOBILE`, and `WEBAPP` to `BROWSER`. Only canonical devices `CTV`, `MOBILE`, and `BROWSER` are eligible; unknown devices such as `BAD` never match.
- Playback `start_utc` and `end_utc`, and credit `event_utc`, are 14-digit numeric UTC timestamps.
- `event_utc` is greater than or equal to the playback `end_utc`.
- The credit's region has an `OPEN` row in `/app/config/region_cutoffs.csv` and `event_utc` is less than or equal to that region's `cutoff_utc`.
- The playback row has not already been consumed. When multiple unused playback rows qualify for one credit, choose the row with the latest `end_utc`; if `end_utc` ties, choose the earliest playback input row.

Write `/app/out/usage_credit_report.csv` with columns `credit_id,stream_id,account_id,device,minutes,reason,status`, preserving credit input order. Matched rows emit the canonical playback `device` and the credit `reason`; unmatched rows leave `device` blank while still writing the credit `minutes` and `reason`. Use only `MATCHED` or `UNMATCHED` in the status column.

Write `/app/out/usage_credit_summary.txt` as `key=value` lines for `matched_count`, `matched_minutes`, `unmatched_count`, and `unmatched_minutes`, counting minutes as positive integers.
