# Operations

The reconciliation job runs as a batch command from `/app` and writes outputs under `/app/out`.

Milestone 3 optional date columns map to internal `play_date` / `credit_date` fields when parsing `scorecards.csv` and `credits.csv`.
The starter defines `loadScorecardes`; renaming it to `loadScorecards` is an expected fix.
Milestone 3 maps CSV `play_date` / `credit_date` to internal date fields (often named RideDate/CreditDate in the starter); CSV column names in instructions are authoritative.
