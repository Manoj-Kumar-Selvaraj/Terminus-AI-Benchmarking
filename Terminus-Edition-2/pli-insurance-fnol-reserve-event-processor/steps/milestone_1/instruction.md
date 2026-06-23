The insurance FNOL reserve adjustment PL/I batch adjudicator is used after a control-deck refresh. Run it through `/app/scripts/run_batch.sh` and repair `/app/src/fnol_batch.pli`, `/app/src/fnol_rules.pli`, or the AWK harness so `/app/data/adjustments.psv` reconciles against `/app/data/claims.psv`.

Milestone 1 combines strict matching, alias canonicalization, and signed reserve direction. See `/app/docs/operations.md` for output schemas. Verifier tests overwrite input PSV files and `/app/src/fnol_rules.pli` at runtime; the batch must honor whatever rules are present when it runs.

Claims require full agreement on `claim_id`, `policy_id`, `loss_unit`, `state_code`, `reserve_cents`, and canonical `coverage_type`. Prefix or substring matches are not enough. Canonicalize `coverage_type` using trimmed case-insensitive `ALIAS_*` declarations in `/app/src/fnol_rules.pli` before matching. A claim row is eligible only when its `status` equals runtime `ELIGIBLE_STATUS`. An adjustment is eligible only when its trimmed `reason` equals runtime `REASON_A`, `REASON_B`, or `REASON_C`, case-insensitively.

Reasons listed in comma-delimited `NEGATIVE_REASON_CODES` must carry a negative `reserve_cents`; all other eligible reasons must carry a positive amount. Summary totals always use absolute adjustment amounts.

Each claim row may be consumed once, and adjustment input order must be preserved in the report. Write `/app/out/reserve_adjustment_report.csv` with exact pipe-delimited columns `action_id|claim_id|policy_id|loss_unit|coverage_type|reserve_cents|reason|status`. Status is exactly `MATCHED` or `UNMATCHED`; unmatched rows leave `coverage_type` blank, and matched rows emit the canonical coverage type from the claim side.

Write `/app/out/reserve_adjustment_summary.txt` with integer keys `matched_count`, `matched_amount_cents`, `unmatched_count`, and `unmatched_amount_cents`. All amount totals must be non-negative.

Later milestones add more `%SET` flags and keep every prior rule. Each milestone verifier re-runs all earlier milestone tests.
