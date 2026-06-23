Apply calendar eligibility from `/app/config/hangar_calendar.txt` while preserving all existing matching, alias, consumption, report, and summary behavior.

A source date is eligible only when it is an eight-digit numeric date listed in the calendar with state `OPEN`, compared case-insensitively. Closed, missing, unlisted, or malformed dates are ineligible.

When several unused source rows qualify for an action, select the row with the latest eligible source date. If dates tie, select the earliest source input row. Track consumption by source row position so distinct rows sharing a record id can each be consumed once.

The report status remains exactly `MATCHED` or `UNMATCHED`, and unmatched rows keep `hangar_class` blank.
