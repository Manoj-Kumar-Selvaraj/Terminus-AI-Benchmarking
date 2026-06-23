# Lab credit reconciliation operations

Run `/app/scripts/run_batch.sh` after updating `/app/data/samples.csv` and `/app/data/credits.csv`. The batch driver clears prior outputs, invokes `reconcile.sh`, and leaves artifacts under `/app/out/`.

Matching compares `sample_id` as a full identifier (not a prefix), trims surrounding spaces, and compares `status` and `payer` case-insensitively. Only `FINAL` samples with allowed payers (`CASH`, `CARD`, `INSURANCE`) are eligible. Legacy aliases `CC`, `INS`, and `CA` normalize to canonical payers in the report.

Dated batches consult `/app/config/cutoff_calendar.txt` for open/closed days. Credits must fall within the configured open-day window relative to each sample `result_date`.
