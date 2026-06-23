# Runbook

1. Inspect inputs with `/app/scripts/inspect_inputs.sh`.
2. Run `/app/scripts/run_batch.sh` to execute `/app/scripts/reconcile.sh`.
3. Review `/app/out/waiver_report.csv` and `/app/out/waiver_summary.json`.
4. Clear outputs with `/app/scripts/clean_outputs.sh` before reruns.

See `/app/docs/record_layout.md` for CSV schemas and `/app/docs/date_gating.md` for calendar rules.
