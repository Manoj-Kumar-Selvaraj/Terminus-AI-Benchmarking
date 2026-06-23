Finish `/app/src/pension_reversal_reconcile.cbl` by adding calendar-aware candidate selection while preserving the existing full-key gates, aliases, report contract, and per-row consumption behavior.

Read `/app/config/posting_calendar.txt` as `YYYYMMDD=STATE`. A source date is eligible only when it is eight numeric digits, appears in the calendar, and its state equals `OPEN` case-insensitively. `CLOS`, blank, malformed, and unlisted entries are not open. The action date must remain numeric and on or after the source date. Status `P`, eligible reasons, canonical bucket equality, amount, account, branch, and full record id still apply.

The optional two-character `allocation_key` documented in `/app/docs/record_layouts.md` follows each source and action branch. A blank action key accepts any source key; a nonblank action key requires equality. Among all unused eligible candidates, choose the latest source date, then the earliest physical source row when dates tie. Mark only that row consumed; duplicate ids or otherwise equal rows remain independently usable.

Write `/app/out/reversal_report.csv` and `/app/out/reversal_summary.txt` with their existing schemas. Preserve action order, canonical matched buckets, blank unmatched buckets, positive totals, and exact `MATCHED` or `UNMATCHED` status values.
