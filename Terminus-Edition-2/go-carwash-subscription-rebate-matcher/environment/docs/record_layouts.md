# Record Layouts

Washes use `wash_id,customer_id,amount_cents,status,plan_tier` in undated batches and may add `wash_date` in dated batches.

Rebates use `wash_id,customer_id,amount_cents,plan_tier` in undated batches and may add `rebate_date` in dated batches.

The report schema is always `wash_id,customer_id,plan_tier,amount_cents,status`.

The summary JSON fields are `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`.
