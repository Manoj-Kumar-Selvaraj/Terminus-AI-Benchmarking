# Date Gating and Earn Lookback

## Dated columns

- `accruals.csv` may include `earn_date` (`YYYY-MM-DD`).
- `adjustments.csv` may include `adjustment_date` (`YYYY-MM-DD`).

When either column is absent on a row, that row is not eligible to match in dated mode.

## Calendar eligibility

`/app/config/cutoff_calendar.txt` lists lines `YYYY-MM-DD open` or `YYYY-MM-DD closed`.

An adjustment can match only when:

- `adjustment_date` is listed as `open`
- `earn_date` is not blank
- `earn_date` is not later than `adjustment_date`

## Earn lookback window

`/app/config/job.properties` defines `earn_lookback_open_days` (shipped value `2`).

When both date columns are present, count calendar days strictly after `earn_date` through and including `adjustment_date` that are explicitly marked `open`. The match is eligible only when that count is less than or equal to `earn_lookback_open_days`. Equal earn and adjustment dates count zero days in the window.

## Selection among eligible accruals

When multiple unused accrual rows match one adjustment, choose the row with the latest `earn_date`. When earn dates tie, choose the earliest accrual input row. Consumption is tracked by accrual row position.
