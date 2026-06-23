# Refund calendar

When dated batches are enabled, finance maintains `/app/config/cutoff_calendar.txt`.
Each non-empty line contains a calendar date and a status token separated by whitespace:

```text
2026-05-01 open
2026-05-02 closed
```

Lines beginning with `#` are comments. Status comparison is case-insensitive. Only dates
explicitly marked open are eligible refund processing days for the dated workflow.

The calendar does not list every calendar day. Dates missing from the file are treated as
not open. Invalid date text should be rejected rather than silently coerced.
