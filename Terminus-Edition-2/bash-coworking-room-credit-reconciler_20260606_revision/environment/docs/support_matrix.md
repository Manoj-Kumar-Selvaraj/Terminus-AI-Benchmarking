# Support matrix

| Batch type | Required inputs | Optional config |
|------------|-----------------|-----------------|
| Undated | `bookings.csv`, `credits.csv` | `plan_aliases.csv` from milestone 2 onward |
| Dated | `bookings.csv` with `booking_date`, `credits.csv` with `credit_date` | `plan_aliases.csv`, `cutoff_calendar.txt`, `run_profile.ini` |

Allowed canonical room plans: `HOTDESK`, `PRIVATE`, `TEAM`.
