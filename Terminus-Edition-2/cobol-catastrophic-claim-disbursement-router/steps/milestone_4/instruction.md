# Milestone 4 — Make committed disbursements restart-safe after ABEND

The incident trace shows duplicate check and EFT instructions after an interrupted run. The batch must now treat payment side effects as committed journal entries and resume safely after `ABEND_AFTER_COMMITS` forces a deterministic failure.

Preserve all previous milestone behavior. Do not delete prior ledgers or queues to hide duplicates. Keep the operator entrypoint `/app/scripts/run_batch.sh` unchanged.

Required behavior:

- Payment instruction ids must be stable as `PAY-<claim_id>-<event_id>`.
- Already committed events from `/app/data/prior_disbursement_ledger.psv` or `/app/out/payment_ledger.psv` must not be re-emitted.
- Already committed events must appear in `/app/out/payment_decision_report.psv` with `decision=ALREADY_COMMITTED`.
- When `ABEND_AFTER_COMMITS=N` is set, the batch must stop after committing N new payment side effects, exit **non-zero**, and write `/app/out/restart_checkpoint.txt`.
- The checkpoint must contain the full last committed instruction id as a literal string, for example `last_committed_instruction_id=PAY-CLM-CHK-EVT-CHK`. A rerun must be able to read this value and resume without duplicating committed rows.
- A clean rerun must resume pending claims, must not duplicate check, EFT, bank verification, or manual review side effects, and must not skip uncommitted eligible claims.
- Queue files, `/app/out/bank_verify_messages.psv`, and `/app/out/payment_ledger.psv` must remain byte-identical across repeated clean reruns when inputs are unchanged. `/app/out/control_totals.psv` must also remain idempotent across clean reruns.

See `/app/docs/restart_recovery.md` and `/app/docs/disbursement_contract.md` for checkpoint and restart semantics.
