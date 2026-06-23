# Restart-Safe Cash Settlement

The nightly router can now be interrupted during release commits. A release is financially complete only when the card exposure ledger and the terminal cash ledger move together. Read `/app/data/terminal_cash.psv` using the contract in `/app/docs/terminal_cash_settlement_contract.md` and write the resulting state to `/app/out/terminal_cash_after.psv`.

Only a ready terminal row for the configured business date with enough available cash may commit. Cash shortages or unavailable terminal cash remain in manual review and cannot be overridden by supervisor approval. Approved review items may commit only when the approval timestamp is a valid 14-digit value no earlier than the release timestamp; denied, missing, malformed, or stale approvals remain in review.

When `ABEND_AFTER_COMMITS` is set, the batch must stop after committing that many releases, leaving recoverable exposure, terminal cash, journal, and checkpoint state. On rerun, read the existing committed journal, skip committed release ids, continue pending releases, and avoid duplicate exposure changes, cash dispense changes, review postings, or journal rows.

Write `/app/out/settlement_manifest.json` exactly as documented in `/app/docs/terminal_cash_settlement_contract.md`. The final release report, card exposure ledger, terminal cash ledger, manual-review queue, risk decisions, committed journal, checkpoint, and settlement manifest must describe the same committed state after restart.
