# Cycle date gating

Skip cycle-date gating only when both the sale settlement date and the chargeback date are absent on legacy records that end after the status byte or merchant id. Apply cycle rules when either side carries a date field on a dated-length record.

On dated-length records, a settlement or chargeback date position that is present but blank (spaces) is ineligible. When cycle rules apply, both dates must be nonblank, listed as `OPEN` in `/app/config/cycle_calendar.txt`, and eligible under the two-open-day window counted strictly after settlement through and including the chargeback date. A chargeback date equal to the settlement date is allowed. Dates missing from the calendar are not open.

When multiple eligible sales remain, choose the latest settlement date; ties break to the latest sale input row.
