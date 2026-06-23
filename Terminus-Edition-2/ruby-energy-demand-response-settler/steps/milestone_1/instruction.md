Fix the Ruby entrypoint `/app/app/reconcile.rb` so it reconciles `/app/data/settlements.csv` against `/app/data/events.csv`; the verifier invokes this Ruby file directly.

Implement milestone 1 of `/app/docs/reconciliation_contract.md`: exact full-key matching, source-row consumption, latest timestamp selection, stable report output, and positive summary totals. Do not enable legacy resource aliases or realtime window eligibility yet.
