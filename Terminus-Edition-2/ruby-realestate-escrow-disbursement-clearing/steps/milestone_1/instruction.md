The escrow disbursement clearing batch is still releasing the wrong source holds. Fix
`/app/app/reconcile.rb`; the verifier runs `ruby /app/app/reconcile.rb` through the existing batch
workflow, so keep the repair in the Ruby application and preserve the shipped CSV schemas and
`/app/out` output paths.  For this first contract, a disbursement action can match only when the
full `escrow_id`, `payee_id`, `trust_id`, `location`, and integer `amount` all match a single unused
hold row; the hold status is exactly `HELD`; the action reason is `CLOSE`, `CORRECT`, or `RELEASE`;
both timestamps are numeric UTC values; the hold timestamp is inside an `OPEN` realtime window for
the same trust; and the action timestamp is strictly after the hold timestamp and not after the window
close. Each hold row can be consumed once, and corrections are processed in input order. When
multiple unused holds qualify for the same action, select the hold with the latest
`source_ts`; if timestamps tie, select the earliest hold row in `/app/data/holds.csv`
input order.  Do not apply legacy kind aliases yet. The source and action `kind` values must already be canonical and
equal, and only `SELLER` and `BROKER` are eligible. Continue writing
`/app/out/disbursement_report.csv` with columns
`action_id,escrow_id,payee_id,trust_id,kind,amount,reason,status`, and
`/app/out/disbursement_summary.txt` with `matched_count`, `matched_amount`, `unmatched_count`, and
`unmatched_amount`.