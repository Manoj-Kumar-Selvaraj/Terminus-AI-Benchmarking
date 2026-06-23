The warehouse dock hold release reconciler in `/app/app/reconcile.rb` is matching correction rows to the wrong session records. Fix it so `/app/data/dock_releases.csv` reconciles against `/app/data/dock_holds.csv`.

Milestone 1 is about the exact reconciliation contract without legacy aliases or realtime window rules. A correction can match only when the full `hold_id`, `shipment_id`, `dock_id`, `door`, and `amount` all match, the source status is the literal `STAGED`, the correction reason is `SHIP`, `SHORT`, `OVERRIDE`, the `load_type` field is one of the canonical values `LTL`, `FTL` on both sides after trimming and case folding, both timestamps are numeric 14-digit UTC values, the correction timestamp `release_ts` is on or after the source timestamp `hold_ts`, and the source row has not already been consumed. Source or correction rows whose `load_type` is anything else, including `PARCEL` and legacy alias codes, are ineligible in this milestone. Non-numeric `hold_ts` or `release_ts` values make the row ineligible.

Preserve correction input order, use `MATCHED` or `UNMATCHED` only, leave `load_type` blank for unmatched rows, and write positive matched and unmatched summary totals.

Write `/app/out/dock_release_report.csv` and `/app/out/dock_release_summary.txt` with the schema documented in this milestone. The reconciler lives in `/app/app/reconcile.rb` and reads `/app/data/dock_holds.csv` and `/app/data/dock_releases.csv`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Write `/app/out/dock_release_report.csv` and `/app/out/dock_release_summary.txt` with the schema documented in this milestone. The reconciler lives in `/app/app/reconcile.rb` and reads `/app/data/dock_holds.csv` and `/app/data/dock_releases.csv`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Write `/app/out/dock_release_report.csv` and `/app/out/dock_release_summary.txt` with the schema documented in this milestone. The reconciler lives in `/app/app/reconcile.rb` and reads `/app/data/dock_holds.csv` and `/app/data/dock_releases.csv`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Write `/app/out/dock_release_report.csv` with columns `release_id,hold_id,shipment_id,dock_id,load_type,amount,reason,status`, preserving correction input order. Matched rows report the canonical source `load_type`; unmatched rows leave `load_type` blank. Write `/app/out/dock_release_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

Input schemas:
- `/app/data/dock_holds.csv`: `hold_id,shipment_id,dock_id,load_type,amount,hold_ts,status,door`
- `/app/data/dock_releases.csv`: `release_id,hold_id,shipment_id,dock_id,load_type,amount,release_ts,reason,door`
- `/app/config/windows.csv`: `dock_id,open_ts,close_ts,state`
