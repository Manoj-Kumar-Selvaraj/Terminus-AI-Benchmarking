# Refund request feed layout

`refunds.csv` is header-addressed. Required columns:

| Column | Meaning |
|--------|---------|
| `appointment_id` | Appointment the client believes they are refunding |
| `client_id` | Account requesting the refund |
| `amount_cents` | Requested refund amount in cents |
| `service_area` | Treatment category named on the refund ticket |

Optional `refund_date` may appear when finance enables dated refund batches. The report must
list refund rows in the same order as this feed.

Amount strings are preserved verbatim in the public report, including leading zeros, even when
internal comparisons use parsed integers. Malformed amount tokens still produce `UNMATCHED`
rows and increment unmatched counters without contributing to cent totals.
