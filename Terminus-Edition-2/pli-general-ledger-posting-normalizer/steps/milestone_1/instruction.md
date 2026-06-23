The general ledger PL/I posting normalizer rejects valid journal matches. Fix `/app/src/posting_batch.pli`, `/app/src/posting_rules.pli`, or the batch harness so `/app/data/postings.psv` normalizes against `/app/data/journal.psv`.

Milestone 1 requires full agreement on `posting_id`, `account`, `amount_cents`, `ctrl_hash`, and `ledger_class`, journal `state` equal to `ELIGIBLE_STATE`, and `entry_type` one of `ENTRY_1`, `ENTRY_2`, or `ENTRY_3`. Each journal row may be consumed once. Preserve entry order. Write `/app/out/posting_report.csv` and `/app/out/posting_summary.txt`.

Status must be exactly `POSTED` or `REJECTED`.
