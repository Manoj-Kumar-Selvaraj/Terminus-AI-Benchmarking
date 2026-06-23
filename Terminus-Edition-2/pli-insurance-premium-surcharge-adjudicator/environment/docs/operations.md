# Insurance Premium Surcharge Adjudicator

Actuarial review compares premium adjustments in `/app/data/adjustments.psv` against policy baselines in `/app/data/policies.psv`. Policy constants are DCL declarations in `/app/src/premium_rules.pli`. Runtime behavior is controlled by `%SET` switches in `/app/src/premium_batch.pli`. Run `/app/scripts/run_batch.sh`.

## Inputs

**Policies** (`/app/data/policies.psv`): `policy_id`, `account_no`, `premium_cents`, `risk_code`, `branch_id`, `ingest_ts`, `state`, `kind_code`.

**Adjustments** (`/app/data/adjustments.psv`): `claim_id`, `policy_id`, `account_no`, `premium_cents`, `risk_code`, `adj_ts`, `opcode`, `branch_id`.

**Fiscal windows** (`/app/config/fiscal_windows.psv`, milestone 3): `account_no`, `open_ts`, `close_ts`, `state`.

Matching, alias, consumption, and fiscal-window behavior are defined in the milestone instructions and `/app/docs/batch_contract.md`.

## Outputs

`/app/out/premium_report.csv`: `claim_id|policy_id|account_no|branch_id|risk_code|premium_cents|opcode|status`

`/app/out/premium_summary.txt`: `valid_count`, `valid_amount_cents`, `invalid_count`, `invalid_amount_cents`
