The hospital bed transfer PL/I reconciler is too loose. Fix `/app/src/reconcile.pli`, `/app/src/reconcile_rules.pli`, or the PL/I runtime harness so `/app/data/transfers.psv` reconciles against `/app/data/beds.psv`.

Milestone 3 keeps every prior rule and adds `/app/config/windows.psv`. Timestamps must be numeric UTC strings, the source timestamp must be inside an explicit open window using `OPEN_WINDOW_STATUS`, the action timestamp must be on or after the source timestamp and not after close, and multiple unused candidates choose latest source timestamp then earliest source row.

The report `status` column must use only the exact strings `MATCHED` and `UNMATCHED`.
