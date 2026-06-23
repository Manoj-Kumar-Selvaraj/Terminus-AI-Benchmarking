# Record Layouts

The reconciler reads CSV files by header name. Required booking headers are `booking_id`, `team_id`, `amount_cents`, `status`, and `room_tier`; dated milestones also use optional `slot_date`. Required refund headers are `booking_id`, `team_id`, `amount_cents`, and `room_tier`; later milestones also use optional `refund_date` and `refund_reason`.

The report is always `/app/out/booking_refund_report.csv` with columns `booking_id,team_id,room_tier,amount_cents,status`. The summary is always `/app/out/booking_refund_summary.json` with integer fields `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`.
