# Report schema

Defined in `/app/config/report_schema.json`.

**refund_report.csv** — one row per refund input row:

```
booking_id,patron_id,seat_zone,amount_cents,status
```

**refund_summary.json** — integer fields `matched_count`, `matched_amount_cents`, `unmatched_count`, `unmatched_amount_cents` (non-negative).
