Continue the ACH reconciler fix in `/app/src/ach_reconcile.cbl`. The core matching from the first pass should stay intact, but settlement entries are still being reused.

Each settlement row can satisfy at most one reversal. Consumption is row-specific, not trace-specific: if two separate eligible settlement rows share the same trace, company, and amount, the first two eligible reversals may consume them in settlement input order, but a third duplicate reversal must remain `UNMATCHED`. Preserve the existing report schema and zero-padded amount behavior in `/app/out/reversal_report.csv`.

Continue to write `/app/out/reversal_report.csv` and `/app/out/reversal_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
