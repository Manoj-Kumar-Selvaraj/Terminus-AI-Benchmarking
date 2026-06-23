# Milestone 3 — Calculate statutory tax and deduction deltas from retro deltas

Gross deltas are correct but tax and deduction side effects still use full corrected totals. See `/app/docs/retro_payroll_contract.md`, `/app/config/tax_rules.psv`, and `/app/config/deduction_caps.psv`.

## Symptom

`tax_delta_cents` is derived from corrected gross minus prior gross tax totals, and `deduction_delta_cents` ignores remaining employee cap.

## Required behavior

- Compute `tax_delta_cents` from the retroactive `gross_delta_cents` using bracket rules in `/app/config/tax_rules.psv`.
- Compute `deduction_delta_cents` as `min(5% of positive gross_delta, remaining cap)` where remaining cap is `cap_cents - prior deduction_cents`.
- Emit `/app/out/tax_delta_report.psv` and `/app/out/control_totals.psv` consistent with `/app/out/adjustment_ledger.psv`.
- Preserve milestones 1–2 behavior.

Example: gross delta `13500` with a 10% marginal bracket on the delta yields tax delta `1350`; 5% of `13500` capped by remaining deduction headroom yields deduction delta `675`.
