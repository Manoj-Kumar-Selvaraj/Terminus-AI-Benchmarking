# Record Layouts

Accruals use `accrual_id,member_id,amount_cents,status,reason` and may include `earn_date`.

Adjustments use `accrual_id,member_id,amount_cents,reason` and may include `adjustment_date`.

Allowed reasons are defined in `/app/config/reasons.csv`. See `/app/docs/reason_allowlist.md` for alias rules and `/app/docs/date_gating.md` for calendar and lookback behavior.
