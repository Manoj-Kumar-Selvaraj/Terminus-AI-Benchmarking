# Batch Reconciliation Contract
Inputs are pipe-separated value files under `/app/data/`. Policy constants are DCL lines in `/app/src/*_rules.pli`.
Runtime switches are `%SET` directives in `/app/src/*_batch.pli`. The harness reads both decks; do not edit `/app/scripts/*.awk`.
Outputs must land in `/app/out/` with stable column order documented in `/app/docs/operations.md`.
