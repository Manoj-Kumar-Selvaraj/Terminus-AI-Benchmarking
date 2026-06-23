# Airline ticket credit reconciler

Entry point: `/app/lib/reconcile.rb`. Reads `/app/data/tickets.csv` and `/app/data/credits.csv`; writes `/app/out/credit_report.csv` and `/app/out/credit_summary.json`. See `matching_rules.md`, `fare_aliases.md`, and `date_gating.md`.
