# Record Layouts

Claim records use type, claim id, reason, amount cents, member id, and status. Claim ids are 12 characters and start with `CLM`; positions 4-11 contain the claim cycle date as `YYYYMMDD`.

Adjustment records use type, claim id, amount cents, and member id.

Cycle-calendar controls use `/app/config/cycle_calendar.txt`. Each row is `YYYYMMDD STATUS`; only `OPEN` status is open, status matching is case-insensitive, and later rows for the same date override earlier rows.
