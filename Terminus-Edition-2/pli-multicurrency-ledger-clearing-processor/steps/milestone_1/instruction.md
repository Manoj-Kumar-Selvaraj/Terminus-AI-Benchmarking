The multicurrency ledger clearing processor holds too many postings on partial key matches. Fix only the PL/I-style control files under `/app/src` so `/app/data/postings.psv` reconciles against `/app/data/ledger.psv`. Do not modify `/app/scripts/run_batch.sh` or `/app/scripts/pli_ledger.awk`; the harness and pipe-delimited output format are fixed even though the report filename ends in `.csv`.

Require full agreement on `txn_id`, `account_id`, `amount_cents`, `currency_code`, and `desk_id`. A ledger row is eligible only when `state` equals `ELIGIBLE_STATE` from `/app/src/ledger_rules.pli`. The posting row's `entry_type` must match one of `REASON_1`, `REASON_2`, or `REASON_3` case-insensitively. Each ledger row may be consumed at most once. Preserve posting order.

When multiple ledger rows qualify for one posting, consume the candidate with the latest `book_ts`; break ties by the earliest ledger row in file order. Read the rule constants dynamically from `/app/src/ledger_rules.pli`; the verifier may replace that file, the ledger, the postings, and the FX-window data with different values.

Currency aliases are not active for this delivery. Do not apply any `ALIAS_*` mappings from the rules file. Currency comparison remains trimmed and case-insensitive, while a `CLEARED` report row preserves the selected ledger row's trimmed currency spelling.

Write `/app/out/ledger_report.csv` as a pipe-delimited file with columns `claim_id`, `txn_id`, `account_id`, `desk_id`, `currency_code`, `amount_cents`, `entry_type`, and `status`. Emit `currency_code` from the matched ledger row on `CLEARED` rows; leave `currency_code` blank on `HELD` rows. Write `/app/out/ledger_summary.txt` as `key=value` lines for `cleared_count`, `cleared_amount_cents`, `held_count`, and `held_amount_cents`, summing `amount_cents` as integers.

Ignore `/app/config/fx_windows.psv` for this run. Status must be exactly `CLEARED` or `HELD`.
