The retail batch trailer reconciler balances claims outside approved settlement windows. Fix `/app/src/trailer_batch.pli`, `/app/src/trailer_rules.pli`, or the batch harness so `/app/data/trailer_claims.psv` reconciles against `/app/data/batches.psv`.

Milestone 3 keeps milestones 1–2 behavior and enforces `/app/config/settlement_windows.psv`. Timestamps are 14-digit UTC strings. Batch `posted_ts` and claim `claim_ts` must both fall inside an open window for the row's `account_no` where window `state` equals `OPEN_SETTLE_STATE` from `/app/src/trailer_rules.pli`.

Status must be exactly `BALANCED` or `REJECTED`.
