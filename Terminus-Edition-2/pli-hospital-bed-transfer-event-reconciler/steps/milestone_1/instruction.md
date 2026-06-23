The hospital bed transfer PL/I reconciler is too loose. Fix `/app/src/reconcile.pli`, `/app/src/reconcile_rules.pli`, or the PL/I runtime harness so `/app/data/transfers.psv` reconciles against `/app/data/beds.psv`.

Milestone 1 matches only when full `bed_id`, `patient_id`, `ward_id`, `nurse_unit`, and `charge_cents` agree, the source status equals `ELIGIBLE_STATUS` from `/app/src/reconcile_rules.pli`, and the action reason is one of `REASON_A`, `REASON_B`, or `REASON_C`. Each source row may be consumed once. Preserve action order, write `/app/out/transfer_report.csv` with the documented schema, blank kind for unmatched rows, and positive cent totals in `/app/out/transfer_summary.txt`.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
