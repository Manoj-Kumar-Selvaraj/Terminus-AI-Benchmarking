Extend `/app/cmd/reconcile/main.go` for dated credit batches. Keep reading `/app/data/passes.csv` and `/app/data/credits.csv` and writing `/app/out/credit_report.csv` and `/app/out/credit_summary.json` with the same schemas and `MATCHED`/`UNMATCHED` labels from earlier milestones.

The verifier may add `valid_until` on passes and `credit_date` on credits. Match only when prior gates still pass, pass status is `ACTIVE` (case-insensitive), `credit_date` is `open` in `/app/config/cutoff_calendar.txt`, and `credit_date` is on or before `valid_until`. When both dates are blank, skip calendar and date-order gates like milestone 2. Missing or closed `credit_date`, or missing `valid_until`, disqualify a pair when dates matter.

If multiple unused passes qualify, pick the latest `valid_until`, then earliest pass row. Consumption is by pass row position, not `pass_id`.

Keep milestone 2 alias rules (`GEN`→`GENERAL`, `TR`→`TOUR`, `MEM`→`MEMBER`). On matched rows emit the canonical credit program after alias normalization; leave `program` blank when unmatched. Summary JSON keys: `matched_count`, `matched_amount_cents`, `unmatched_count`, `unmatched_amount_cents` as integers.
