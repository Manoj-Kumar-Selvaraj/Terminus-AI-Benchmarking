# Incident 2026-06-12 — false DENIED on SVC-PAYMENTS

Audits with identical five-key tuples were denied when two mandates shared a prefix-only `mandate_id` match. Review `KEY_COMPARE` and `CONSUME` in the batch deck.
