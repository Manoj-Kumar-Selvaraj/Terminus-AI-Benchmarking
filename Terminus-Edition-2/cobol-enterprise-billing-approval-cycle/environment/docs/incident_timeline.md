# Billing incident timeline

23:10 UTC: nightly enterprise billing approval started for production cycle.

23:22 UTC: operations found accounts with many small usage rows bypassing dual approval because the COBOL job selected approval tier from the last usage line.

23:36 UTC: duplicate prior-run batches were billed again when the prior ledger check did not compare both account and batch.

23:49 UTC: dual-threshold invoices showed only regional approval trace rows; finance approval never ran.

00:07 UTC: an ABEND inside an account group produced a partial invoice. Restart replayed already processed rows and changed invoice totals.
