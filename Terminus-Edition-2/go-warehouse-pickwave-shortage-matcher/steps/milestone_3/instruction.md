The warehouse pickwave shortage reconciler in `/app/cmd/reconcile/main.go` is matching correction rows to the wrong pick records. Fix that Go source file so `/app/data/shortages.csv` reconciles against `/app/data/picks.csv`, using `/app/config/windows.csv` for the active realtime window rules. A correction matches a source row only when the full `pick_id`, `sku`, `wave_id`, `location`, and `amount` all match, the source status is the literal `FULFILLED`, the correction reason is `DAMAGE`, `MISSING`, or `MISROUTE`, and the `kind` matches after alias normalization. Kind aliases must be normalized before matching: `EA` means `EACH`, `CS` means `CASE`, `PL` means `PALLET`. The canonical match-eligible `kind` values remain exactly `EACH`, `CASE`, or `PALLET`; unknown normalized values such as `BAD` are never match-eligible.

The source timestamp and correction timestamp must be numeric UTC timestamps. The source timestamp must be inside an `OPEN` window for the same `wave_id` in `/app/config/windows.csv`, and the correction timestamp must be on or after the source timestamp but not after the window close. Closed, missing, malformed, or unlisted windows are not eligible. If multiple unused source rows qualify, choose the latest source timestamp and then the earliest source input row. Each source row can be consumed once.

Input schemas:
- `/app/data/picks.csv`: `pick_id,sku,wave_id,kind,amount,source_ts,status,location`
- `/app/data/shortages.csv`: `action_id,pick_id,sku,wave_id,kind,amount,action_ts,reason,location`
- `/app/config/windows.csv`: `wave_id,open_ts,close_ts,state`

Write `/app/out/shortage_report.csv` with columns `action_id,pick_id,sku,wave_id,kind,amount,reason,status`, preserving correction input order. Matched rows report the canonical source `kind`; unmatched rows leave `kind` blank. Write `/app/out/shortage_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

Milestone 3 keeps every milestone 1 and milestone 2 rule, including the post-normalization canonical `kind` gate for `EACH`, `CASE`, or `PALLET`. The realtime window file is authoritative: only numeric timestamps in explicitly `OPEN` windows are eligible, closed, missing, malformed, or unlisted windows are not eligible, actions must occur after the source timestamp and before the window close, and multiple unused candidates are resolved by latest source timestamp with earliest input row as the tie-breaker.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
