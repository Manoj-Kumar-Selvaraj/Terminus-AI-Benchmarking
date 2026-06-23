# Terminal cash settlement contract

An ATM release is not complete until the authorization exposure and terminal cash ledgers agree. The input ledger is `/app/data/terminal_cash.psv`:

`terminal_id|business_date|available_cash_cents|dispensed_today_cents|release_count_today|state`

Only a `READY` terminal row for the configured business date with enough available cash can commit. A commit subtracts the release amount from `available_cash_cents`, adds it to `dispensed_today_cents`, and increments `release_count_today`. Review and unmatched releases do not mutate the cash ledger.

The resulting ledger is written to `/app/out/terminal_cash_after.psv` using the same schema. Restart recovery must use the prior output ledger and the committed release journal together so a previously committed release cannot dispense cash twice.

The downstream settlement loader consumes `/app/out/settlement_manifest.json`. It contains exactly:

- `schema_version`: integer `1`
- `checkpoint_release_id`: the last committed release id, or an empty string
- `committed_release_count`: number of committed journal rows
- `committed_amount_cents`: amount summed from committed journal rows
- `review_release_count`: releases still routed to manual review in the completed run
- `terminal_balances`: terminal rows sorted by `terminal_id`, each containing `terminal_id`, integer `available_cash_cents`, and integer `dispensed_today_cents`

Supervisor approvals are valid only when status is `APPROVED`, `approved_ts` is a numeric 14-digit timestamp, and `approved_ts` is not earlier than the release timestamp. Approval cannot override missing, blocked, wrong-date, malformed, or insufficient terminal cash.
