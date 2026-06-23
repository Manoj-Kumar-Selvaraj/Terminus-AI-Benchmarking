# Support matrix

Allowed stall_type values are PRODUCE, CRAFT, and CHECK. Legacy refund aliases are PRD -> CRAFT, CRT -> PRODUCE, FOD -> CHECK (case-insensitive).

Only stall rows with status `RESERVED` or `confirmed` are eligible for matching.

Stall policy and market-day calendar gates are optional; the starter ignores `/app/config/stall_policy.csv` and `/app/config/market_calendar.txt`.
