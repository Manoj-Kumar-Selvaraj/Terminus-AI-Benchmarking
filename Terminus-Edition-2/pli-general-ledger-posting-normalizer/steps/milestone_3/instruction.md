The general ledger PL/I posting normalizer rejects valid journal matches. Fix `/app/src/posting_batch.pli`, `/app/src/posting_rules.pli`, or the batch harness.

Milestone 3 keeps prior rules and adds `/app/config/book_windows.psv`. Book and post timestamps must fall inside an open book window per account using `OPEN_BOOK_STATE`. Tie-break on latest `book_ts` then earliest journal row.
