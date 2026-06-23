Extend `/app/lib/reconcile.rb` for dated rebate batches. `invoices.csv` may include `service_date` and `rebates.csv` may include `rebate_date`.

**Backward compatibility:** Date rules apply only when **both** files include their date column (`service_date` in invoices and `rebate_date` in rebates). If either column is absent, ignore `/app/config/cutoff_calendar.txt` and match exactly as milestone 2 (aliases, consumption, and all prior gates still apply).

When both date columns are present, a rebate can match only when all prior criteria still pass, `rebate_date` is listed as `open` in `/app/config/cutoff_calendar.txt`, and `rebate_date` is not later than the invoice `service_date`. Missing, closed, or unlisted `rebate_date` values are not eligible. An invoice with missing `service_date` is not eligible.

If multiple unused invoice rows match one rebate, choose the row with the latest `service_date`. If `service_date` values tie, choose the earliest invoice input row (lowest row position in `invoices.csv`). Consumption is by row position, not `invoice_id`, so duplicate ids in separate rows remain separate. Later rebates in `rebates.csv` input order see only rows not yet consumed; a wrong row choice can leave no eligible invoice for a later rebate even when amounts and bays still align.

Keep milestone 2 aliases (`EXP` → `EXPRESS`, `STD` → `STANDARD`, `DTL` → `DETAIL`), canonical matched `bay` output, blank unmatched `bay`, and the existing report and summary schemas.

Continue to write `/app/out/rebate_report.csv` and `/app/out/rebate_summary.json` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
