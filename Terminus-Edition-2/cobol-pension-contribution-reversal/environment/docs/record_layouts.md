# Fixed-Width Layouts

Source: type 1, record_id 12, account 8, bucket 3, amount 10, source_date 8, status 1, branch 4.

Action: type 1, record_id 12, account 8, bucket 3, amount 10, action_date 8, reason 3, branch 4.

Milestone 3 may append a two-character `allocation_key` after `branch` on both record types. A blank action key does not filter candidates; a nonblank action key must equal the source key. This field is used for candidate eligibility but is not emitted in the report.

`/app/config/posting_calendar.txt` uses one `YYYYMMDD=STATE` entry per line. `OPEN` is case-insensitive; `CLOS` means closed, and malformed or unlisted dates are not open.
