# Release Report Schema

`/app/out/release_report.csv` must use this exact header:

`release_id,hold_id,card_id,terminal_id,channel,amount_cents,reason,status`

Rules:
- One output row per release input row in release-file order.
- `status` is exactly `MATCHED` or `UNMATCHED`.
- Matched rows emit the canonical hold channel; unmatched rows leave `channel` blank.
