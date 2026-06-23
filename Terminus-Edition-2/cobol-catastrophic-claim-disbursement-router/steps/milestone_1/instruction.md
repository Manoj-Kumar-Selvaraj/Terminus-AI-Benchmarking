# Milestone 1 — Restore catastrophic-claim eligibility and reject precedence

The overnight catastrophic-claim payment batch is emitting payment instructions for claims that operations expected to reject before routing. Use the incident notes in `/app/evidence/incident_log.txt`, the policy tables under `/app/config`, and the seed files under `/app/data` to restore the eligibility stage.

Focus on `/app/src/catclaim_router.cbl`. Preserve the current command contract: `/app/scripts/run_batch.sh` must remain the way operators start the batch, and outputs must remain under `/app/out`.

Required behavior:

- A claim can advance only when the policy exists, the policy is active, the claim member matches the policy member, adjudication is approved, the diagnosis is catastrophic, required authorization is present, and the amount is positive.
- When several problems exist on the same claim, choose the first reason from `/app/config/reject_precedence.psv`.
- Rejected claims must be written to `/app/out/reject_ledger.psv`, must appear in `/app/out/payment_decision_report.psv` with `decision=REJECT`, and must not create payment side effects in `/app/out/check_queue.psv`, `/app/out/eft_queue.psv`, or `/app/out/payment_ledger.psv`.
- Eligible claims must appear in `/app/out/payment_decision_report.psv` with `decision=ELIGIBLE_PENDING_ROUTE` and must not appear in `/app/out/reject_ledger.psv`.
- Milestone 1 does not need to finalize payment rails.
- Output schemas are defined in `/app/docs/disbursement_contract.md`.
- Do not hardcode the provided seed rows; the verifier rewrites the input files.
