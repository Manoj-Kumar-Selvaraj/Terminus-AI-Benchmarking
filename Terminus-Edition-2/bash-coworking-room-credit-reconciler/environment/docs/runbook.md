# Coworking credit reconciliation runbook

1. Export fresh `bookings.csv` and `credits.csv` into `/app/data`.
2. Confirm `/app/config/plan_aliases.csv` reflects current room-plan aliases.
3. For dated batches, refresh `/app/config/cutoff_calendar.txt` and `/app/config/run_profile.ini`.
4. Run `/app/scripts/run_batch.sh` and inspect `/app/out/credit_report.csv` plus `/app/out/credit_summary.json`.
5. Investigate unmatched rows against front-desk booking logs before manual adjustments.
