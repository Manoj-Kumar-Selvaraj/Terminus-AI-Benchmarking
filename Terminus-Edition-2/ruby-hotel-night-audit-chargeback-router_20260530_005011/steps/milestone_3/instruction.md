The realtime hotel night audit chargeback reconciler is matching correction rows to the wrong source records. Fix it so `/app/data/chargebacks.csv` reconciles against `/app/data/folios.csv`, using `/app/config/windows.csv` for the active realtime window rules.

A correction matches a source row only when the full `folio_id`, `guest_id`, `property_id`, `location`, and `amount` all match, the source status is the literal `POSTED`, the correction reason is `DISPUTE`, `DUPLICATE`, or `NOAUTH`, and the kind matches after alias normalization. Kind aliases must be normalized before matching: `CC` means `CARD`, `CSH` means `CASH`, `PTS` means `POINTS`.

The source timestamp and correction timestamp must be numeric UTC timestamps. The source timestamp must be inside an `OPEN` window for the same `property_id` in `/app/config/windows.csv`, and the correction timestamp must be on or after the source timestamp but not after the window close. Closed, missing, malformed, or unlisted windows are not eligible. If multiple unused source rows qualify, choose the latest source timestamp and then the earliest source input row. Each source row can be consumed once.

Write `/app/out/chargeback_report.csv` with columns `action_id,folio_id,guest_id,property_id,kind,amount,reason,status`, preserving correction input order. Matched rows report the canonical source kind; unmatched rows leave `kind` blank. Write `/app/out/chargeback_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, with amounts counted as positive integers.

Milestone 3 keeps every milestone 1 and milestone 2 rule. The realtime window file is authoritative: only numeric timestamps in explicitly `OPEN` windows are eligible, closed, missing, malformed, or unlisted windows are not eligible, actions must occur after the source timestamp and before the window close, and multiple unused candidates are resolved by latest source timestamp with earliest input row as the tie-breaker.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
