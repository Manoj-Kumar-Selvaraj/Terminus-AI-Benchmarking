# Milestone 3 — Add payment-rail verification and control totals

Once facility routing was fixed, high-value EFTs were still sent directly to the payment rail before bank verification completed. The batch also needs reliable control totals so support can compare payment, review, and reject outcomes after the run.

Preserve the existing `/app/scripts/run_batch.sh` interface and all milestone 1 and 2 behavior. Use the legacy threshold deck at `/app/config/payment_policy.pli` and the verification fixture at `/app/data/bank_verification_responses.psv`.

Required behavior:

- High-value EFT claims at or above the configured bank-verification threshold must not enter `/app/out/eft_queue.psv` unless a matching verification response is approved.
- A matching bank verification response is approved only when `claim_id`, `event_id`, and `bank_account` match and `status` is exactly `APPROVED` after trimming and uppercasing.
- Unverified high-value EFT claims must emit `/app/out/bank_verify_messages.psv` and route to manual review with a stable reason.
- Lower-value EFT claims and approved high-value EFT claims may enter `/app/out/eft_queue.psv`.
- Identity conflicts must route to manual review before payment-rail side effects. Identity conflicts are defined in `/app/docs/disbursement_contract.md`: sentinel `identity_token` values `CONFLICT`, `MISMATCH`, or `DUPLICATE_IDENTITY`, or the same nonblank token appearing for multiple `member_id` values in the same batch.
- `/app/out/payment_ledger.psv` and `/app/out/control_totals.psv` must reconcile queued payment, manual-review, and reject counts and amounts.
- `/app/out/control_totals.psv` must include the metric names documented in `/app/docs/disbursement_contract.md`: `payment_queued`, `manual_review`, `rejected`, `check_queue`, `eft_queue`, `bank_verify`, and `committed_ledger`.
