# Batch Reconciliation Contract
Inputs are pipe-separated value files under `/app/data/`. Policy constants are DCL lines in `/app/src/*_rules.pli`; load `ELIGIBLE_STATE`, reason codes, aliases, and direction rules at runtime rather than hardcoding sample values.
Runtime switches are `%SET` directives in `/app/src/*_batch.pli` (for example `LEDGER_MODE=ON`, `WINDOW_MODE=ON`). The harness reads both decks; repair `/app/scripts/run_batch.sh` and, when needed, `/app/scripts/pli_wire.awk`.
Outputs must land in `/app/out/` with stable pipe-delimited column order documented in `/app/docs/operations.md`.
