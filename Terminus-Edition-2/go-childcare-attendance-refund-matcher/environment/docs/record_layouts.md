# Childcare refund reconciliation layouts

The batch CLI reads `/app/data/sessions.csv` and `/app/data/refunds.csv`. CSV columns are header-addressed and may include extra columns. Required session fields are `session_id`, `guardian_id`, `amount_cents`, `status`, and `room`; dated batches also include `attendance_date`. Required refund fields are `session_id`, `guardian_id`, `amount_cents`, and `room`; later batches may include `refund_date`, `refund_method`, and `settlement_date`.
