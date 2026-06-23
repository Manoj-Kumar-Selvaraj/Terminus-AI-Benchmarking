Add a configuration-driven eligibility gate to `/app/lib/reconcile.rb` while preserving all milestone 1-3 behavior.

The program must still read `/app/data/bookings.csv` and `/app/data/refunds.csv`, then write `/app/out/refund_report.csv` and `/app/out/refund_summary.json` with the same schema, ordering, alias normalization, dated matching rules, tie-breaking, and positive summary cents.

For this milestone, use `/app/config/methods.csv` with columns `fund,enabled`. After seat-zone alias normalization, a candidate booking is eligible only when its canonical seat zone is enabled in this config (`enabled=true`, case-insensitive and whitespace-tolerant). Treat this mapping as:
- `ORCH` uses `fund=GENERAL`
- `MEZZ` uses `fund=CAPITAL`
- `BALC` uses `fund=RELIEF`

Missing rows, malformed rows, or rows with `enabled=false` are ineligible. This methods gate applies in both dated and undated modes, and all prior criteria must still be enforced.
