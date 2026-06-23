The laundry locker hold release reconciler in `/app/app/reconcile.rb` is matching correction rows to the wrong session records. Fix it so `/app/data/locker_releases.csv` reconciles against `/app/data/locker_holds.csv`.

Milestone 1 is about the exact reconciliation contract without legacy aliases or realtime window rules. A correction can match only when the full `hold_id`, `customer_id`, `site_id`, `locker`, and `amount` all match, the source status is the literal `LOADED`, the correction reason is `PICKUP`, `REFUND`, `OVERRIDE`, the `service_tier` field is one of the canonical values `WASH`, `DRY` on both sides after trimming and case folding, both timestamps are numeric 14-digit UTC values, the correction timestamp `release_ts` is on or after the source timestamp `hold_ts`, and the source row has not already been consumed. Source or correction rows whose `service_tier` is anything else, including `COMBO` and legacy alias codes, are ineligible in this milestone. Non-numeric `hold_ts` or `release_ts` values make the row ineligible.

Preserve correction input order, use `MATCHED` or `UNMATCHED` only, leave `service_tier` blank for unmatched rows, and write positive matched and unmatched summary totals.

Write `/app/out/locker_release_report.csv` and `/app/out/locker_release_summary.txt` with the schema documented in this milestone. The reconciler lives in `/app/app/reconcile.rb` and reads `/app/data/locker_holds.csv` and `/app/data/locker_releases.csv`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Write `/app/out/locker_release_report.csv` and `/app/out/locker_release_summary.txt` with the schema documented in this milestone. The reconciler lives in `/app/app/reconcile.rb` and reads `/app/data/locker_holds.csv` and `/app/data/locker_releases.csv`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Write `/app/out/locker_release_report.csv` and `/app/out/locker_release_summary.txt` with the schema documented in this milestone. The reconciler lives in `/app/app/reconcile.rb` and reads `/app/data/locker_holds.csv` and `/app/data/locker_releases.csv`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Write `/app/out/locker_release_report.csv` with columns `release_id,hold_id,customer_id,site_id,service_tier,amount,reason,status`, preserving correction input order. Matched rows report the canonical source `service_tier`; unmatched rows leave `service_tier` blank. Write `/app/out/locker_release_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

Input schemas:
- `/app/data/locker_holds.csv`: `hold_id,customer_id,site_id,service_tier,amount,hold_ts,status,locker`
- `/app/data/locker_releases.csv`: `release_id,hold_id,customer_id,site_id,service_tier,amount,release_ts,reason,locker`
- `/app/config/windows.csv`: `site_id,open_ts,close_ts,state`
