Extend `/app/lib/reconcile.rb` so `/app/config/methods.csv` is authoritative for which canonical arrangements may match while preserving every milestone 1, milestone 2, and milestone 3 rule.

The methods file is a CSV with columns `arrangement,enabled`. Normalize the `arrangement` value after trimming and case folding using the same alias rules as credits: `BQT` means `BOUQUET`, `CTR` means `CENTERPIECE`, and `ARC` means `ARCH`. A credit can match only if the matched canonical arrangement is present in `methods.csv` with `enabled` set to `true`, case-insensitively. Disabled arrangements, missing arrangements, blank arrangement names, malformed rows, unknown arrangements, and non-`true` enabled values are not eligible. Ignore malformed method rows instead of crashing.

The date rules from milestone 3 still apply: when `delivery_date` and `credit_date` columns are present, `credit_date` must be open in `/app/config/cutoff_calendar.txt`, must not be later than `delivery_date`, missing dates are ineligible, the latest eligible `delivery_date` wins, tied dates use the earliest order row, and consumption is tracked per order input row.

Continue to write `/app/out/credit_report.csv` and `/app/out/credit_summary.json` with the same schemas, status labels, blank unmatched `arrangement`, canonical matched `arrangement`, and positive integer summary totals from earlier milestones.
