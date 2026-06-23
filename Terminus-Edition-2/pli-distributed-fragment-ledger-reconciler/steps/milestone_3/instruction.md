The distributed fragment PL/I reconciler orphans valid merges. Fix `/app/src/fragment_batch.pli`, `/app/src/fragment_rules.pli`, or the batch harness.

Milestone 3 keeps prior rules and adds `/app/config/shard_windows.psv`. Ingest and merge timestamps must fall inside an open shard window per channel using `OPEN_SHARD_STATE`. Tie-break on latest `ingest_ts` then earliest fragment row.
