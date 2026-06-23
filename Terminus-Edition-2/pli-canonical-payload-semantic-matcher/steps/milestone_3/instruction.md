The canonical payload semantic matcher accepts checks outside approved schema compare windows. Fix `/app/src/semantic_batch.pli`, `/app/src/semantic_rules.pli`, or the batch harness so `/app/data/actual.psv` reconciles against `/app/data/expected.psv`.

Milestone 3 keeps milestones 1–2 behavior and enforces `/app/config/compare_windows.psv`. Timestamps are 14-digit UTC strings. Expected `recv_ts` and actual `check_ts` must both fall inside an open window for the row's `schema_id` where window `state` equals `OPEN_COMPARE_STATE` from `/app/src/semantic_rules.pli`.

Status must be exactly `EQUAL` or `DIFFER`.
