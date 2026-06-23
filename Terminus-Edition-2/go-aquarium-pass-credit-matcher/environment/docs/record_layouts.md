# Record Layouts

Passes use `pass_id,guest_id,amount_cents,status,program`. The `status` column stores pass lifecycle values; only `ACTIVE` passes are eligible for credit matching.

Credits use `pass_id,guest_id,amount_cents,program`.
