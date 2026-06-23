# Lab credit reconciliation runbook

1. Place input CSVs at `/app/data/samples.csv` and `/app/data/credits.csv`.
2. For dated batches, ensure `/app/config/cutoff_calendar.txt` lists each relevant day as `open` or `closed`.
3. Run `/app/scripts/run_batch.sh`.
4. Inspect `/app/out/credit_report.csv` and `/app/out/credit_summary.json`.

Use `/app/scripts/clean_outputs.sh` to remove stale artifacts between runs. Use `/app/scripts/inspect_inputs.sh` to print a quick row count summary before reconciliation.
