The EV charging session release reconciler in `/app/app/reconcile.rb` is matching correction rows to the wrong session records. Fix it so `/app/data/session_releases.csv` reconciles against `/app/data/charge_sessions.csv`.

Milestone 1 is about the exact reconciliation contract without legacy aliases or realtime window rules. A correction can match only when the full `session_id`, `vehicle_id`, `station_id`, `port`, and `amount` all match, the source status is the literal `ACTIVE`, the correction reason is `STOP`, `FAULT`, `OVERRIDE`, the `rate_plan` field is one of the canonical values `LEVEL2`, `DCFC` on both sides after trimming and case folding, both timestamps are numeric UTC values, the correction timestamp `release_ts` is on or after the source timestamp `plug_ts`, and the source row has not already been consumed. Source or correction rows whose `rate_plan` is anything else, including `FLEET` and legacy alias codes, are ineligible in this milestone. Non-numeric `plug_ts` or `release_ts` values make the row ineligible.

Preserve correction input order, use `MATCHED` or `UNMATCHED` only, leave `rate_plan` blank for unmatched rows, and write positive matched and unmatched summary totals.

Write `/app/out/ev_release_report.csv` with columns `release_id,session_id,vehicle_id,station_id,rate_plan,amount,reason,status`, preserving correction input order. Matched rows report the canonical source `rate_plan`; unmatched rows leave `rate_plan` blank. Write `/app/out/ev_release_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

Input schemas:
- `/app/data/charge_sessions.csv`: `session_id,vehicle_id,station_id,rate_plan,amount,plug_ts,status,port`
- `/app/data/session_releases.csv`: `release_id,session_id,vehicle_id,station_id,rate_plan,amount,release_ts,reason,port`
- `/app/config/windows.csv`: `station_id,open_ts,close_ts,state`
