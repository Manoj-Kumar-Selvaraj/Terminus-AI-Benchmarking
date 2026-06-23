# Milestone 2 — Add facility trust and expedited-check routing

After eligibility was restored, the next run still emitted expedited checks for facilities that the operations desk considers blocked or untrusted. Use `/app/config/facility_trust.psv`, `/app/config/payment_policy.pli`, and `/app/evidence/payment_queue_diff.txt` to make the payment routing stage respect facility trust.

Continue editing `/app/src/catclaim_router.cbl`. Preserve all milestone 1 reject behavior and output schemas from `/app/docs/disbursement_contract.md`.

Required behavior:

- Sanctioned facilities must route to `/app/out/manual_review_queue.psv` with the appropriate reason and must not create payment instructions.
- Untrusted facilities without an emergency override must route to manual review.
- Expedited checks are allowed only for catastrophic diagnoses marked as expedited, within the configured expedited threshold from `EXPEDITED_CHECK_LIMIT_CENTS`, and from a trusted facility or an allowed emergency override.
- Standard check payments that are not expedited may still be queued in `/app/out/check_queue.psv` when the facility is not blocked.
- Check queue rows must use `priority=EXPEDITED` or `priority=NORMAL` as defined in `/app/docs/disbursement_contract.md`.
- `/app/out/payment_decision_report.psv` must use `decision=PAYMENT_QUEUED` for queued payments and `decision=MANUAL_REVIEW` for manual-review outcomes.
