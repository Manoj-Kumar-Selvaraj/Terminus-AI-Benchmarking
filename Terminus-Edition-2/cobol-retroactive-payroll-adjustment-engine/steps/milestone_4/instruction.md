# Milestone 4 — Make employee-boundary restart idempotent after ABEND

Operations reproduced duplicate adjustments after `ABEND_AFTER_EMPLOYEES`. See `/app/evidence/abend_trace.log` and `/app/docs/retro_payroll_contract.md`.

## Symptom

A partial run appends adjustments again on rerun and does not checkpoint committed employees.

## Required behavior

- Commit adjustments at employee boundaries during processing.
- When `ABEND_AFTER_EMPLOYEES=N` interrupts the batch, exit non-zero after employee `N` and write `/app/out/restart_checkpoint.txt` as `LAST_COMMITTED_EMPLOYEE|<employee_id>`.
- A clean rerun must skip employees at or before the checkpoint and must not duplicate existing `adjustment_id` values.
- Preserve effective-dating for mid-period `YYYYMMDD` compensation rows. When `/app/config/pay_period_workdays.psv` provides `period`, `total_workdays`, and `post_change_workdays`, prorate corrected gross between the previous applicable row and the new row instead of selecting either row for the whole period.
- Preserve tax, deduction, reject, and control-total behavior from earlier milestones.
