# Operations

The reconciliation job runs as a batch command from `/app` and writes outputs under `/app/out`.

The CSV headers in the task instructions are authoritative. Some internal names in the Go package are older operational names kept for compatibility with existing run scripts and monitoring dashboards.

Dated voucher runs may include optional `order_date` and `voucher_date` fields. Calendar entries are read from `/app/config/cutoff_calendar.txt` during the run.
