# Operations

The reassignment batch consumes each eligible accession row at most once and emits rows in reassignment input order.
Operations staff use `/app/out/reassignment_report.csv` and `/app/out/reassignment_summary.txt` as the observable run artifacts.

For the final reconciliation profile, reason eligibility and realtime windows are loaded from `/app/config/reasons.csv` and `/app/config/windows.csv` at runtime.
