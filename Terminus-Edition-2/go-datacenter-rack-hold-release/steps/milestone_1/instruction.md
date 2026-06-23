Fix the realtime datacenter rack hold release reconciler in `/app/cmd/reconcile/main.go` so `/app/data/releases.csv` reconciles against `/app/data/holds.csv`. See `/app/docs/record_layouts.md` for column names and the baseline matching contract.

Ignore `/app/config/windows.csv` entirely for this milestone. A correction matches only when `hold_id`, `asset_id`, `aisle_id`, `rack`, and `amount` all match exactly, the source status is the literal `LOCKED`, the correction reason is `DECOMM`, `MIGRATE`, or `OVERRIDE`, the `access_tier` is `HOT` or `WARM` on both sides after trimming and case folding, both timestamps are 14-digit numeric UTC values, the correction timestamp `release_ts` is on or after the source timestamp `hold_ts`, and the source row has not already been consumed. Rows with any other `access_tier`, or non-numeric or non-14-digit timestamps, are ineligible.

If more than one source row satisfies the contract for one correction, consume the first qualifying source row in file order. Preserve correction input order, use only the status labels `MATCHED` and `UNMATCHED`, leave `access_tier` blank for unmatched rows, and write positive matched and unmatched summary totals.

Write `/app/out/rack_release_report.csv` with columns `release_id,hold_id,asset_id,aisle_id,access_tier,amount,reason,status`. Matched rows report the canonical source `access_tier`; unmatched rows leave `access_tier` blank. Write `/app/out/rack_release_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

Keep the deliverable as a Go CLI compiled from the source under `/app` with `/usr/local/go/bin/go`.
