# Spa refund reconciliation

Nightly batch reconciliation ties client refund requests to completed appointment rows.
Finance exports two CSV feeds under `/app/data/`:

- `appointments.csv` — services that were delivered and may back a refund
- `refunds.csv` — refund requests submitted by the front desk or online portal

The reconciler at `/app/lib/reconcile.rb` is invoked through `/app/scripts/run_batch.sh`.
It must regenerate `/app/out/refund_report.csv` and `/app/out/refund_summary.json` on every
run. Downstream accounting consumes those artifacts; partial writes or appended rows are not
accepted.

Operational config under `/app/config/` may be present for alias tables, open refund dates,
service policy, and per-client limits. Not every deployment stage uses every file. When a
config file is absent or a column is missing from a feed, the reconciler should preserve
backward-compatible behavior for earlier rollout stages.
