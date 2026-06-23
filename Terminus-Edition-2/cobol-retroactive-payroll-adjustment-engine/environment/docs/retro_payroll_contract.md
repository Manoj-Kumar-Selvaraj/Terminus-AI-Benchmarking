# Retroactive payroll adjustment contract

Corrections to closed pay periods must create immutable adjustment entries. Prior payroll and compensation files under `/app/data` are evidence and must not be rewritten.

The batch is invoked with `/app/scripts/run_batch.sh`. All outputs are pipe-separated value (PSV) files under `/app/out`.

## Effective dating

For each row in `/app/data/prior_payroll.psv`, select the compensation row from `/app/data/compensation_history.psv` with the latest `effective_from` that is still `<=` the payroll `period`. Rows with no applicable compensation must not receive fabricated adjustments.

`effective_from` may be either `YYYYMM` or `YYYYMMDD`. When a `YYYYMMDD`
compensation row starts inside the closed payroll period and
`/app/config/pay_period_workdays.psv` supplies that period, compute corrected
gross by prorating between the previous applicable compensation row and the
new row. The calendar file has columns `period`, `total_workdays`, and
`post_change_workdays`; pre-change workdays are
`total_workdays - post_change_workdays`.

## Gross component order

Corrected gross is `base_cents + allowance_cents + overtime`, where overtime is `base_cents * overtime_hours * overtime_rate_bp / 10000`. Do not multiply overtime over allowance or over the full gross subtotal.

## Tax and deduction deltas

- `tax_delta_cents` is computed from the retroactive `gross_delta_cents` using `/app/config/tax_rules.psv`, not by subtracting taxes on full corrected vs prior totals.
- `deduction_delta_cents` is `min(5% of positive gross_delta, remaining employee cap)` where remaining cap is `cap_cents - prior deduction_cents` from `/app/config/deduction_caps.psv`.

## Restart and ABEND

When `ABEND_AFTER_EMPLOYEES=N` interrupts a run, a subsequent clean rerun must resume after the last fully committed employee. Already committed adjustment IDs must not be duplicated. Checkpoint file format:

```text
LAST_COMMITTED_EMPLOYEE|<employee_id>
```

## Output files

| File | Columns |
|------|---------|
| `adjustment_ledger.psv` | `adjustment_id`, `employee_id`, `period`, `gross_delta_cents`, `tax_delta_cents`, `deduction_delta_cents`, `net_delta_cents`, `status` |
| `period_delta_report.psv` | `employee_id`, `period`, `prior_gross_cents`, `corrected_gross_cents`, `gross_delta_cents`, `decision` |
| `reject_ledger.psv` | `employee_id`, `period`, `reason_code` (`COMPENSATION_RULE_MISSING` when no effective row exists) |
| `tax_delta_report.psv` | `employee_id`, `period`, `gross_delta_cents`, `tax_delta_cents`, `deduction_delta_cents`, `net_delta_cents` |
| `control_totals.psv` | `metric`, `value` (`adjustment_count`, `gross_delta_cents`, `tax_delta_cents`, `net_delta_cents`) |
| `restart_checkpoint.txt` | single line `LAST_COMMITTED_EMPLOYEE|<employee_id>` after each committed employee boundary |

Adjustment IDs follow `ADJ-<employee_id>-<period>`.
