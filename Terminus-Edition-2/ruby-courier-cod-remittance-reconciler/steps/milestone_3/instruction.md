Harden realtime window eligibility in `/app/app/reconcile.rb` while preserving every milestone 1 and milestone 2 rule and output schema.

Milestone 3 focuses on `/app/config/windows.csv` edge cases: only numeric `open_ts` and `close_ts` values inside explicitly `OPEN` windows for the same `station_id` are eligible; closed, malformed, missing, and unlisted `station_id` windows must reject otherwise-valid matches. Corrections with `action_ts` before the window `open_ts` or after the window `close_ts` must stay `UNMATCHED`. When multiple unused deliveries still qualify, choose the latest `source_ts` and then the earliest delivery input row.

Keep writing `/app/out/cod_remittance_report.csv` and `/app/out/cod_remittance_summary.txt` with the same columns, ordering, alias behavior, and summary accounting from earlier milestones. Use only `MATCHED` or `UNMATCHED` in the report.
