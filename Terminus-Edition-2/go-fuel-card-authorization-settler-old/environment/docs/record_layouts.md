# Record Layouts

`/app/data/authorizations.csv` and `/app/data/reversals.csv` are header-addressed CSV files. Required authorization columns are `auth_id`, `fleet_id`, `batch_id`, `kind`, `amount`, `source_ts`, `status`, and `location`. Required reversal columns are `action_id`, `auth_id`, `fleet_id`, `batch_id`, `kind`, `amount`, `action_ts`, `reason`, and `location`. Extra columns may appear and must not affect reconciliation.

Amounts are positive base-10 integer cents. Reversal amount strings are reported after trimming exactly as supplied, including leading zeros, while summary totals use their integer value.
