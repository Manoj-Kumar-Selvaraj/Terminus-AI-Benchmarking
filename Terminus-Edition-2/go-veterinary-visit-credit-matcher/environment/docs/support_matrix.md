# Support matrix

Allowed clinic values are MAIN, MOBILE, and CHECK. Legacy credit aliases are MN -> MOBILE, VAN -> MAIN, URG -> CHECK (case-insensitive).

Only visit rows with status `CLOSED` or `posted` are eligible for matching.

Clinic policy and clinic-day calendar gates are optional; the starter ignores `/app/config/clinic_policy.csv` and `/app/config/clinic_calendar.txt`.
