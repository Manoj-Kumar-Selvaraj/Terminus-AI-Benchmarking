# Record Layouts

Bills use `tab_id,patron_id,amount_cents,status,pour_tier`. Dated batches may add `tab_date`.

Credits use `tab_id,patron_id,amount_cents,pour_tier`. Dated batches may add `adjust_date`; method-gated batches may add `adjust_method`.
