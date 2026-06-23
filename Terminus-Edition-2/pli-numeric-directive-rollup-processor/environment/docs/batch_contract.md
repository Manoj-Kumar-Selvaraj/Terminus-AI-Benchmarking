# Batch Contract

Edit `/app/src/rollup_rules.pli` and `/app/src/rollup_batch.pli` only unless a milestone explicitly requires AWK validation fixes. The gawk harness under `/app/scripts/pli_rollup.awk` is the runtime engine.

Legacy decks referenced `%SET ALIAS_NORMALIZE ON`; the current control token is `ALIAS_MODE`. Do not enable obsolete names.

Outputs must match `/app/docs/operations.md`, `/app/docs/rollup_report_schema.md`, and `/app/docs/rollup_summary_contract.md`. The rollup report is **pipe-delimited** (`|`), not comma-separated CSV.
