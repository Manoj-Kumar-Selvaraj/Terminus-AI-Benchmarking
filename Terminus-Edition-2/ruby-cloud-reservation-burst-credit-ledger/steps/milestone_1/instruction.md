The realtime cloud reservation burst credit reconciler in `/app/app/reconcile.rb` is matching correction rows to the wrong source records. Fix it so `/app/data/credits.csv` reconciles against `/app/data/seat_events.csv`, using `/app/config/windows.csv` for active realtime window rules.

A correction matches only when `event_id`, `account_id`, `reservation_id`, `region`, and integer `amount` agree; the source status is `ALLOCATED`; the reason is `BURST`, `RECLAIM`, or `CORRECT`; both timestamps are numeric; and `credit_ts` is on or after `reserve_ts`. The source `reserve_ts` must fall inside an `OPEN` window for the same `reservation_id`, and `credit_ts` must not exceed that window's `close_ts`. Closed, missing, malformed, or unlisted windows are ineligible.

Do not use `sku_type` as a pairwise matching key. Each row must independently contain a canonical `CPU` or `GPU` value to be eligible, but source and correction values do not need to be equal. `MEM` and legacy alias tokens are not eligible in this initial contract. Each source row can be consumed at most once.

When several unused source rows qualify, choose the latest `reserve_ts`; ties break by earliest source input row. Preserve correction input order, use only `MATCHED` or `UNMATCHED`, and leave `sku_type` blank on unmatched rows.

Write `/app/out/seat_credit_report.csv` with header `credit_id,event_id,account_id,reservation_id,sku_type,amount,reason,status`. Matched rows report the selected source's canonical `sku_type`. Write `/app/out/seat_credit_summary.txt` as `key=value` lines for `matched_count`, `matched_amount`, `unmatched_count`, and `unmatched_amount`, using positive integers without decimal points.
