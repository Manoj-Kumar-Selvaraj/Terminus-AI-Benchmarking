# Date gating

Dated batches add `pledge_due` on pledges and `adjustment_date` on adjustments.

When neither CSV includes those columns, skip date gating and keep milestone 1–2 behavior.

When date columns are present:

- `adjustment_date` must appear as `open` in `/app/config/cutoff_calendar.txt`.
- `adjustment_date` must not be later than `pledge_due` (equal dates are eligible).
- Missing, closed, or unlisted adjustment dates are ineligible.
- Pledges with missing `pledge_due` are ineligible in dated mode.

If multiple unused pledges match one adjustment, choose the latest `pledge_due`; on a tie, choose the earliest pledge input row. Consumption is by row index, not `pledge_id`.
