# Reporting outputs

Each successful batch writes two artifacts under `/app/out/`:

## refund_report.csv

Per-refund status in input order. Finance uses this file for exception queues.

Typical columns: `appointment_id`, `client_id`, `service_area`, `amount_cents`, `status`.
Matched rows carry the canonical service area; unmatched rows leave `service_area` blank.
Status labels are `MATCHED` or `UNMATCHED`.

## refund_summary.json

Aggregate counters for the treasury dashboard:

- `matched_count` / `unmatched_count` — row counts
- `matched_amount_cents` / `unmatched_amount_cents` — positive integer cent totals

Invalid amount rows increment unmatched counts but do not add to either amount total.
