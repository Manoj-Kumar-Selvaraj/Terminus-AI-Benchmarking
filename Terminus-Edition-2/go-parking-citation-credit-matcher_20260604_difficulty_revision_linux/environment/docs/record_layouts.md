# Record Layouts

Citations use `citation_id,plate_id,amount_cents,status,zone`.

Credits use `citation_id,plate_id,amount_cents,zone`.

Dated batches may add `due_date` to citations and `credit_date` to credits.

Policy-gated batches may add `credit_method` to credits. The report schema does not include `credit_method`.
