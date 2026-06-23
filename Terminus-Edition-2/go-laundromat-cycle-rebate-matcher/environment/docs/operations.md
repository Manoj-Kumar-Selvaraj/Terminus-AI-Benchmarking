# Operations

The reconciliation job runs as a batch command from `/app` and writes outputs under `/app/out`.

Milestone 3 optional date columns map to internal `cycle_date` / `rebate_date` fields when parsing `cycles.csv` and `rebates.csv`.
The starter defines `loadCyclees`; renaming it to `loadCycles` is an expected fix.
Milestone 3 maps CSV `cycle_date` / `rebate_date` to internal date fields (often named RideDate/CreditDate in the starter); CSV column names in instructions are authoritative.
