The FNOL reserve batch must enforce final policy limits and subrogation holds while preserving all prior outputs. Continue through `/app/scripts/run_batch.sh`, keep milestone 1 through 3 behavior, and keep all existing report, summary, ledger, and restart schemas.

Use `/app/config/policy_limits.psv` with pipe-delimited columns `policy_id|max_reserve_cents`. Limits are applied after alias canonicalization and after replay duplicate suppression. For each `policy_id`, matched absolute adjustment amounts consume the limit in adjustment input order. If an adjustment would exceed the configured limit, mark it `UNMATCHED`, leave `coverage_type` blank, do not consume a claim row, and record a `POLICY_LIMIT` exception. Later adjustments for other policies must continue processing.

Use `/app/config/subrogation_holds.psv` with columns `action_id|hold_reason`. A listed adjustment action must be `UNMATCHED`, must not consume a claim row, and must record a `SUBROGATION_HOLD` exception.

Write `/app/out/reserve_exceptions.csv` with exact pipe-delimited header `action_id|claim_id|policy_id|reason|detail`. Write `/app/out/reserve_position.txt` with exact pipe-delimited header `policy_id|limit_cents|used_cents|remaining_cents`. Exception rows and reserve positions must be deterministic and must not require network calls, clock time, or external services.
