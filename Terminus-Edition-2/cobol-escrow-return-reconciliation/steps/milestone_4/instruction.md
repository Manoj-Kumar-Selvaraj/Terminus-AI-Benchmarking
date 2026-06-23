Milestone 4 adds one more production requirement: the settlement-cycle window must be configurable without code changes.

Extend the batch in `/app/src/wire_returns.cbl` so it reads `cycle_window_open_days` from `/app/config/job.properties` (same `key=value` file that already contains the report and summary paths). Use this value as the maximum allowed number of open cycle days between the wire settlement date and the return date.

- If `cycle_window_open_days` is missing or blank, default to `2` (the milestone 3 behavior).
- The window rule is unchanged except for the limit: count only `OPEN` calendar dates strictly after the settlement date through the return date, and the return is eligible only when the open-day count is \( \le \) `cycle_window_open_days`.
- Keep all prior matching gates, consumption rules, date parsing, latest-settlement selection, tie-breakers, and output schemas intact.

Continue to write `/app/out/wire_return_report.csv` and `/app/out/wire_return_summary.txt` with the same schemas, status labels, blank unmatched fields, and summary keys from the earlier milestone.
