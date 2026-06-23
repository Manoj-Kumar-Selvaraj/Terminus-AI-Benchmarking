# Catastrophic claim disbursement contract

The nightly batch routes fictional catastrophic-claim payments into side-effect queues.
A claim may be paid only after eligibility, facility trust, payment-rail, and idempotency
checks succeed. Rejects and manual reviews are terminal for that run and must not emit
payment instructions. Payment instruction identifiers must remain stable across restarts:
`PAY-<claim_id>-<event_id>`.

Outputs are pipe-delimited PSV files under `/app/out`. See `/app/docs/disbursement_contract.md`
for normative schemas. The batch may be interrupted after committed payment side effects
using `ABEND_AFTER_COMMITS`. A rerun must not append duplicate ledger or queue rows.

## payment_decision_report.psv

Columns: `claim_id`, `event_id`, `policy_id`, `amount_cents`, `decision`, `reason_code`, `instruction_id`

`decision` values:

- `ELIGIBLE_PENDING_ROUTE` — eligible in milestone 1 before payment rails are finalized
- `REJECT` — eligibility failure; `reason_code` comes from `/app/config/reject_precedence.psv`
- `MANUAL_REVIEW` — routed to review instead of payment rails
- `PAYMENT_QUEUED` — payment instruction created for check or EFT rail
- `ALREADY_COMMITTED` — event already present in prior or output ledger; no new side effects

## reject_ledger.psv

Columns: `claim_id`, `event_id`, `reason_code`

## check_queue.psv

Columns: `instruction_id`, `claim_id`, `event_id`, `payee_type`, `amount_cents`, `priority`

`priority` values: `EXPEDITED` or `NORMAL`

## manual_review_queue.psv

Columns: `claim_id`, `event_id`, `reason_code`, `amount_cents`, `required_action`

Identity conflicts use `reason_code` `IDENTITY_CONFLICT`. A claim is an identity
conflict when either:

- `identity_token` is one of `CONFLICT`, `MISMATCH`, or `DUPLICATE_IDENTITY`
  after trimming and uppercasing; or
- the same nonblank `identity_token` appears in the current batch for more than
  one `member_id`.

## bank_verify_messages.psv

Columns: `instruction_id`, `claim_id`, `event_id`, `bank_account`, `amount_cents`, `reason_code`

For high-value EFT routing, `bank_verification_responses.psv` treats
`status=APPROVED` as the only approved verification status. Other statuses,
missing rows, or mismatched `claim_id`/`event_id`/`bank_account` values are
unverified and must route to manual review with `BANK_VERIFY_REQUIRED`.

## eft_queue.psv

Columns: `instruction_id`, `claim_id`, `event_id`, `bank_account`, `amount_cents`

## payment_ledger.psv

Columns: `instruction_id`, `claim_id`, `event_id`, `rail`, `amount_cents`, `status`

## control_totals.psv

Columns: `metric`, `count`, `amount_cents`

Required metric names: `payment_queued`, `manual_review`, `rejected`, `check_queue`,
`eft_queue`, `bank_verify`, `committed_ledger`

## restart_checkpoint.txt

Plain-text checkpoint marker written after a deterministic ABEND. Required lines:

```text
last_committed_instruction_id=PAY-<claim_id>-<event_id>
last_committed_event_id=<event_id>
committed_count=<integer>
```

The `last_committed_instruction_id` value must contain the full stable payment
instruction id as a single token (for example `PAY-CLM-CHK-EVT-CHK`). A restart
must resume from this checkpoint without duplicating committed queue or ledger rows.
When `ABEND_AFTER_COMMITS` triggers, the batch must exit non-zero after writing
this file.
