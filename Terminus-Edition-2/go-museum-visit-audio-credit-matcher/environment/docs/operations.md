# Operations

The reconciliation job runs as a batch command from `/app` and writes outputs under `/app/out`.

Milestone 3 optional date columns map to internal `visit_date` / `credit_date` fields when parsing `visits.csv` and `audio_credits.csv`.
The starter defines `loadVisites`; renaming it to `loadVisits` is an expected fix.
Milestone 3 maps CSV `visit_date` / `credit_date` to internal date fields (often named RideDate/CreditDate in the starter); CSV column names in instructions are authoritative.
