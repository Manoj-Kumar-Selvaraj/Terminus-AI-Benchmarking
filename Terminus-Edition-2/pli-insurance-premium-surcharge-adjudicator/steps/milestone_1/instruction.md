Repair the insurance premium surcharge adjudicator under `/app` so adjustments in `/app/data/adjustments.psv` reconcile against policies in `/app/data/policies.psv`.

`/app/scripts/run_batch.sh` is the required batch entrypoint and invokes the authoritative implementation in `/app/scripts/pli_premium.awk`. Keep that command path and the existing PL-I-style control-deck and rule-deck formats compatible; do not replace the workflow with a separate uninvoked program.

A policy can validate an adjustment only when the cleaned `policy_id`, `account_no`, integer `premium_cents`, `risk_code`, and `branch_id` agree in full. Compare text keys case-insensitively. The policy `state` must equal `ELIGIBLE_STATE` from `/app/src/premium_rules.pli`, and the adjustment `opcode` must equal `REASON_1`, `REASON_2`, or `REASON_3`, also case-insensitively.

Each policy input row may be consumed once. Preserve adjustment input order. When several unused policies qualify for the same adjustment, select the candidate with the latest numeric 14-digit `ingest_ts`; break ties by the earliest policy row in file order. Equal-timestamp rows with the same five matching fields are equivalent, but each physical row remains independently consumable. Ignore `/app/config/fiscal_windows.psv`.

Write `/app/out/premium_report.csv` as a pipe-separated file with this exact header:

`claim_id|policy_id|account_no|branch_id|risk_code|premium_cents|opcode|status`

Emit one row per adjustment. Status is exactly `VALID` or `INVALID`. A valid row emits the selected policy row's trimmed `risk_code` spelling; an invalid row leaves `risk_code` blank.

Write `/app/out/premium_summary.txt` as exactly these `key=value` lines:

`valid_count`, `valid_amount_cents`, `invalid_count`, `invalid_amount_cents`

Counts and amount totals are non-negative integers, and amounts are summed from adjustment `premium_cents`.
