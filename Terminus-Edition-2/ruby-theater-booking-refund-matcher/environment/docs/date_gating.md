# Date gating

Optional columns: `show_date` on bookings, `refund_date` on refunds.

When neither file includes those columns, skip date gating and keep milestone 1-2 behavior.

When present:

- Both `refund_date` and `show_date` must be open in `/app/config/cutoff_calendar.txt`.
- `refund_date` must be before `show_date`.
- Count open dates strictly after `refund_date` through and including `show_date`; at least two open dates are required.
- Missing, closed, or unlisted dates are ineligible.
- Multiple eligible bookings: pick the latest `show_date`; ties use earliest booking input row.
- Consumption is by row index, not `booking_id`.
