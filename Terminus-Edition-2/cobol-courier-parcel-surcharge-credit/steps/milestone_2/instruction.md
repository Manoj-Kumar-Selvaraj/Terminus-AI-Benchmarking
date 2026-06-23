Legacy service-tier values have started arriving in the courier credit feed. Update `/app/src/parcel_credit_reconcile.cbl` so `/app/scripts/run_batch.sh` handles them without changing the established matching, report, or summary contracts.

Each input record starts with a one-byte record type prefix. The `record_id` starts after that prefix; do not include the leading `S` or `A` byte in comparisons or report output. The program is compiled as free-format COBOL with `cobc -x -free -O2`, so rewritten code and comments must be valid in free-format COBOL. The report `status` column must contain only `MATCHED` or `UNMATCHED`.

Legacy action service_tier aliases must be normalized before matching and report output: `ST` means `STD`, `NX` means `NXT`, `SM` means `SAM`. Matched rows report the canonical source service_tier; unmatched rows leave that column blank. Each source row can still be consumed at most once, with the earliest eligible action winning when duplicate action rows target the same source row.

Continue to write `/app/out/surcharge_credit_report.csv` and `/app/out/surcharge_credit_summary.txt` with the established schemas, status labels, blank unmatched fields, and summary keys.
