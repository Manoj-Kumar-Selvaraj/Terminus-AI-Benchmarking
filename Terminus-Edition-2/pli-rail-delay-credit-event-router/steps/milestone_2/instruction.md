The rail platform delay credit PL/I reconciler is too loose. Fix `/app/src/reconcile.pli`, `/app/src/reconcile_rules.pli`, or the PL/I runtime harness so `/app/data/credits.psv` reconciles against `/app/data/trips.psv`.

Milestone 2 keeps every milestone 1 rule and adds aliases declared as `ALIAS_*` PL/I values in `raw=>canonical` form. Normalize aliases case-insensitively before matching and emit only canonical `fare_type` values for matched rows. Unknown kinds stay unmatched.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
