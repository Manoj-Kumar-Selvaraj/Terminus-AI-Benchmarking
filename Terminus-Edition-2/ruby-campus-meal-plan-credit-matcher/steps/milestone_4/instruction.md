Extend `/app/lib/reconcile.rb` so `/app/config/methods.csv` is authoritative for which canonical meal-plan locations may match while preserving all existing matching, alias, date, consumption, trace, and output behavior.

The methods file is a CSV with columns `location,enabled`. Normalize `location` after trimming and case folding using the same aliases as credits: `DIN` means `DINING`, `CAF` means `CAFE`, and `MKT` means `MARKET`. A credit can match only if the matched canonical location is present in `methods.csv` with `enabled` set to `true`, case-insensitively. Disabled locations, missing locations, blank location names, malformed rows, unknown locations, and non-`true` enabled values are not eligible. Ignore malformed method rows instead of crashing.

The existing date rules still apply: when `cycle_end` and `credit_date` columns are present, `credit_date` must be open in `/app/config/cutoff_calendar.txt`, must not be later than `cycle_end`, missing dates are ineligible, the latest eligible `cycle_end` wins, tied values use the earliest plan row, and consumption is tracked per plan input row.

Continue to regenerate `/app/out/credit_report.csv`, `/app/out/credit_summary.json`, and `/app/out/plan_consumption.csv` with their established schemas.
