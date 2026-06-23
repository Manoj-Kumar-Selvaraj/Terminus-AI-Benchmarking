# Milestone 1 — Resolve effective-dated compensation for each closed payroll period

The retroactive payroll batch applied the newest compensation row to every historical period. Use `/app/evidence/incident_log.txt`, `/app/docs/retro_payroll_contract.md`, and `/app/data` to fix effective dating in `/app/src/payroll_runtime.py`.

## Symptom

`active_comp` ignores payroll period when choosing compensation history, creating false adjustments for periods that predate a newer row (for example EMP-A period `202602`).

## Required behavior

- For each closed period in `/app/data/prior_payroll.psv`, select the latest compensation row whose `effective_from` is still `<=` that period.
- Do not modify `/app/data/prior_payroll.psv` or `/app/data/compensation_history.psv`; write outputs only under `/app/out`.
- Write `/app/out/adjustment_ledger.psv` and `/app/out/period_delta_report.psv` for valid corrections.
- Missing effective compensation must write `/app/out/reject_ledger.psv` with `reason_code` exactly `COMPENSATION_RULE_MISSING` and must not fabricate an adjustment.
- Run via `/app/scripts/run_batch.sh`. Verifier replaces data files; do not hardcode seed employees.
