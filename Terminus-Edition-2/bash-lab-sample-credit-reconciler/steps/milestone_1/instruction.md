Fix the Bash reconciler in `/app/scripts/reconcile.sh`. The starter script has multiple independent bugs; repair the reconciliation logic rather than hardcoding output files.

It must read `/app/data/samples.csv` and `/app/data/credits.csv`, then write `/app/out/credit_report.csv` and `/app/out/credit_summary.json`. A credit matches only when `sample_id`, `patient_id`, amount, `FINAL` sample status, and an allowed `payer` all line up. Allowed `payer` values are `CASH`, `CARD`, `INSURANCE`. Compare ids as full identifiers, trim incidental surrounding spaces, compare status and `payer` case-insensitively, and consume each sample row at most once.

The report schema is `sample_id,patient_id,payer,amount_cents,status` in credit input order. Use `MATCHED` and `UNMATCHED`; leave `payer` blank for unmatched rows. The JSON summary must contain `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents` with positive integer cents.
