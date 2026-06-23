# Date Gating and Waiver Window

## Dated columns

- `fines.csv` may include `due_date` (`YYYY-MM-DD`).
- `waivers.csv` may include `waiver_date` (`YYYY-MM-DD`).

Both dates must be present and eligible for a match in dated mode.

## Calendar eligibility

`/app/config/cutoff_calendar.txt` lists lines `YYYY-MM-DD open` or `YYYY-MM-DD closed`.

Both `waiver_date` and `due_date` must be listed as `open`. The waiver date must not be later than the due date.

## Open-day window

`/app/config/run_profile.ini` defines `waiver_open_window_days` (shipped value `2`).

Count calendar days strictly after `waiver_date` through and including `due_date` that are explicitly marked `open`. The match is eligible only when that count is less than or equal to `waiver_open_window_days`. Same-day waiver and due dates count zero days in the window.

## Selection among eligible fines

When multiple unused fine rows match one waiver, choose the row with the latest `due_date`. When due dates tie, choose the earliest fine input row. Consumption is tracked by fine row position.
