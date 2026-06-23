The rail platform delay credit PL/I reconciler is too loose. Fix `/app/src/reconcile.pli`, `/app/src/reconcile_rules.pli`, or the PL/I runtime harness so `/app/data/credits.psv` reconciles against `/app/data/trips.psv`.

Milestone 1 matches only when full `trip_id`, `rider_id`, `station_id`, `platform`, and `credit_cents` agree, the source status equals `ELIGIBLE_STATUS` from `/app/src/reconcile_rules.pli`, and the action reason is one of `REASON_A`, `REASON_B`, or `REASON_C`. Each source row may be consumed once. Preserve action order, write `/app/out/delay_credit_report.csv` with the documented schema, blank kind for unmatched rows, and positive cent totals in `/app/out/delay_credit_summary.txt`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
