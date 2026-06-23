Fix the template reconciliation CLI in `/app/cmd/reconcile/main.go`. Read `/app/data/records.csv` and `/app/data/adjustments.csv`, then write `/app/out/template_report.csv` and `/app/out/template_summary.json`.

A adjustment matches a record only when cleaned `record_id`, `account_id`, `amount_cents`, `ACTIVE` status (case-insensitive), and tier all align. Allowed tiers are `TIER_A` and `TIER_B`. Each record row can be consumed at most once.

Report columns: `record_id,account_id,tier,amount_cents,status`. One row per adjustment in adjustment input order. Use exactly `MATCHED` or `UNMATCHED`. Matched rows emit the record tier; unmatched rows leave `tier` blank.

Summary JSON keys: `matched_count`, `matched_amount_cents`, `unmatched_count`, `unmatched_amount_cents` with positive integer cent totals.

Compile with `/usr/local/go/bin/go`.
