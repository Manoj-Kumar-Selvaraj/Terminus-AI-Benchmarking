# Record Layouts

Settlement records are fixed width:

- `S` record type
- 15 character trace
- 3 character SEC code
- 10 digit amount in cents
- 1 character direction, `C` or `D`
- 8 digit effective date
- 8 character company id
- 1 character settlement status

Reversal records are fixed width:

- `R` record type
- 15 character original trace
- 3 character reason code
- 10 digit amount in cents
- 8 digit reversal date
- 8 character company id

Return windows use `/app/config/business_calendar.txt`. Each line is `YYYYMMDD OPEN` or `YYYYMMDD CLOSED`; only open dates after the settlement date and through the reversal date count against the window. Later rows for the same date override earlier rows, and status matching is case-insensitive.
