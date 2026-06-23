Extend `/app/lib/reconcile.rb` for dated credit batches. `plans.csv` may include `cycle_end` and `credits.csv` may include `credit_date`.

**Backward compatibility:** If the `cycle_end` column is absent from the `/app/data/plans.csv` header, skip the cycle-end gate entirely. The missing-value rule applies only when that column is present and a row's value is blank. Apply the same rule to `credit_date` in `/app/data/credits.csv`: if the column is absent, skip the credit-date and calendar gates; if the column is present and a value is blank, that credit is not eligible.

When both date columns are present, a credit can match only when all existing criteria pass, `credit_date` is listed as `open` in `/app/config/cutoff_calendar.txt`, and `credit_date` is not later than the plan `cycle_end`.

If multiple unused plan rows match one credit, choose the row with the latest `cycle_end`. If `cycle_end` values tie, choose the earliest plan input row. Consumption is by physical row position, not `plan_id`, so duplicate identifiers in separate rows remain separate.

Regenerate `/app/out/plan_consumption.csv` with this exact header:

```text
credit_row,plan_row,cycle_end
```

Write one trace row for each matched credit in credit input order. `credit_row` and `plan_row` are zero-based physical data-row positions; CSV headers are not counted. `cycle_end` is the selected plan row's value and is blank in undated mode. Unmatched credits do not appear in this trace.

Keep the existing aliases (`DIN` to `DINING`, `CAF` to `CAFE`, `MKT` to `MARKET`), canonical matched `location` output, blank unmatched `location`, and the established report and summary schemas.

Continue to write `/app/out/credit_report.csv` and `/app/out/credit_summary.json` with the established status labels, blank unmatched fields, and summary keys.
