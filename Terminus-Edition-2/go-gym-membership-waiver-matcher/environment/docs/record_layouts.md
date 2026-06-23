# Record Layouts

Memberships use `membership_id,member_id,amount_cents,status,plan`.

Waivers use `membership_id,member_id,amount_cents,plan`.

Dated waiver batches may add `renewal_date` to memberships and `waiver_date` to waivers.

Policy-gated waiver batches may add `waiver_method` to waivers. The report schema does not include `waiver_method`.
