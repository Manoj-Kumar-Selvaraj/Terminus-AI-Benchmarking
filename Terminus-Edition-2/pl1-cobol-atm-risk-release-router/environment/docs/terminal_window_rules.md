# Terminal Window Rules (Milestone 3)

`/app/config/terminal_windows.psv` lists `terminal_id`, `open_ts`, `close_ts`, and `state` for each terminal.

A hold is eligible only when its terminal has a window whose `state` matches `OPEN_WINDOW_STATUS` case-insensitively. Closed, missing, malformed, or unlisted terminals are ineligible.

Hold and release timestamps must be numeric 14-digit UTC strings. The hold timestamp must satisfy `open_ts <= hold_ts <= close_ts`. The release timestamp must satisfy `hold_ts <= release_ts <= close_ts`.

When multiple unused holds qualify, choose the latest hold timestamp and, when timestamps tie, the earliest hold data row by zero-indexed position in `/app/data/holds.psv` (first data row after the header is index 0).
