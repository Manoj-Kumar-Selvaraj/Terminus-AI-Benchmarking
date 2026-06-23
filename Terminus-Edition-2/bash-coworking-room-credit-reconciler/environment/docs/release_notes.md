# Release notes

## 2026-04 batch tooling

- Header-addressed CSV parsing for reordered booking and credit exports.
- Runtime plan alias normalization from `/app/config/plan_aliases.csv`.
- Dated credit batches gated by `/app/config/cutoff_calendar.txt` and `max_open_days_back` in `/app/config/run_profile.ini`.
