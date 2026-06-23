The hospital bed hold release reconciler in `/app/app/reconcile.rb` is matching correction rows to the wrong session records. Fix it so `/app/data/bed_releases.csv` reconciles against `/app/data/bed_holds.csv`.

Milestone 1 is about the exact reconciliation contract without legacy aliases or realtime window rules. A correction can match only when the full `hold_id`, `patient_id`, `ward_id`, `room`, and `amount` all match, the source status is the literal `OCCUPIED`, the correction reason is `DISCH`, `TRANS`, `OVERRIDE`, the `care_room` field is one of the canonical values `ACUTE`, `OBS` on both sides after trimming and case folding, both timestamps are numeric 14-digit UTC values, the correction timestamp `release_ts` is on or after the source timestamp `hold_ts`, and the source row has not already been consumed. Source or correction rows whose `care_room` is anything else, including `ICU` and legacy alias codes, are ineligible in this milestone. Non-numeric `hold_ts` or `release_ts` values make the row ineligible.

Preserve correction input order, use `MATCHED` or `UNMATCHED` only, leave `care_room` blank for unmatched rows, and write positive matched and unmatched summary totals.

Write `/app/out/bed_release_report.csv` and `/app/out/bed_release_summary.txt` with the schema documented in this milestone. The reconciler lives in `/app/app/reconcile.rb` and reads `/app/data/bed_holds.csv` and `/app/data/bed_releases.csv`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Write `/app/out/bed_release_report.csv` and `/app/out/bed_release_summary.txt` with the schema documented in this milestone. The reconciler lives in `/app/app/reconcile.rb` and reads `/app/data/bed_holds.csv` and `/app/data/bed_releases.csv`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Write `/app/out/bed_release_report.csv` and `/app/out/bed_release_summary.txt` with the schema documented in this milestone. The reconciler lives in `/app/app/reconcile.rb` and reads `/app/data/bed_holds.csv` and `/app/data/bed_releases.csv`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.

Write `/app/out/bed_release_report.csv` with columns `release_id,hold_id,patient_id,ward_id,care_room,amount,reason,status`, preserving correction input order. Matched rows report the canonical source `care_room`; unmatched rows leave `care_room` blank. Write `/app/out/bed_release_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

Input schemas:
- `/app/data/bed_holds.csv`: `hold_id,patient_id,ward_id,care_room,amount,hold_ts,status,room`
- `/app/data/bed_releases.csv`: `release_id,hold_id,patient_id,ward_id,care_room,amount,release_ts,reason,room`
- `/app/config/windows.csv`: `ward_id,open_ts,close_ts,state`
