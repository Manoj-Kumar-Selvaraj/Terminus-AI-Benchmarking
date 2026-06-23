# Lab sample CSV record layout

`samples.csv` and `credits.csv` are comma-delimited files without quoted commas. Columns may be reordered and extra columns may appear; address fields by header name.

Sample rows use `sample_id`, `patient_id`, `amount_cents`, `status`, and `payer`. Dated batches add `result_date` as a strict `YYYY-MM-DD` value.

Credit rows use `sample_id`, `patient_id`, `amount_cents`, and `payer`. Dated batches add `credit_date` as a strict `YYYY-MM-DD` value.

The report file is `/app/out/credit_report.csv` and uses `sample_id,patient_id,payer,amount_cents,status` with one row per credit input row. The summary file is `/app/out/credit_summary.json` and stores integer counts and positive cent totals derived from the report.

`/app/config/payer_clearance_caps.csv` lists optional cumulative clearance limits per canonical payer (`payer,cap_cents`). Payers not listed are uncapped.
