# Milestone 2 — Restore ordered gross component recalculation

After effective dating is restored, overtime gross deltas are still wrong. See `/app/docs/component_order.md` and `/app/config/component_order.pli`.

## Symptom

Overtime is applied as a multiplier over `base + allowance` instead of adding `base * hours * rate_bp / 10000` after base and allowance.

## Required behavior

- Corrected gross = `base_cents + allowance_cents + (base_cents * overtime_hours * overtime_rate_bp / 10000)`.
- Preserve milestone 1 effective dating, reject ledger behavior, and immutable data files.
- Continue writing `/app/out/adjustment_ledger.psv`, `/app/out/period_delta_report.psv`, and `/app/out/reject_ledger.psv`.
- Keep `/app/scripts/run_batch.sh` as the operator entry point.

Example: EMP-B period `202603` with 2 overtime hours should yield gross delta `13500` when prior gross was `67500`.
