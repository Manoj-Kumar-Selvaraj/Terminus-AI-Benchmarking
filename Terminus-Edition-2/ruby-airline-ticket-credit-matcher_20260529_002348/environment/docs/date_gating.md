# Date gating

Optional columns: `flight_date` on tickets, `credit_date` on credits.

When **neither** CSV includes those columns, skip date gating and use milestone 1–2 rules only. Ruby CSV returns `nil` for missing columns when the header is absent; that is not the same as a blank cell under a present header.

When date columns exist:

- `credit_date` must be `open` in `/app/config/cutoff_calendar.txt`
- `credit_date` must not be later than `flight_date` (equal days eligible)
- Blank or ineligible dates reject matching; missing `flight_date` rejects in dated mode
- Multiple eligible tickets: latest `flight_date`; ties → earliest ticket row
