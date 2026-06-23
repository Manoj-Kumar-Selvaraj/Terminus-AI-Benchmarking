# Operations

The reconciliation job runs as a batch command from `/app` and writes outputs under `/app/out`.

The starter Go source intentionally contains legacy generic identifiers such as Trip, Credit, and PassType; those names are part of the buggy implementation surface. The CSV headers and task instructions are authoritative for required behavior.

Milestone 3 maps CSV `print_date` / `credit_date` to internal date fields (often named RideDate/CreditDate in the starter); CSV column names in instructions are authoritative.
