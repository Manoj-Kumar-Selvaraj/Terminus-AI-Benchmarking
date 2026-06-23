The workload manifest consistency auditor accepts checks outside approved rollout windows. Fix `/app/src/manifest_batch.pli`, `/app/src/manifest_rules.pli`, or the batch harness so `/app/data/rollout_checks.psv` reconciles against `/app/data/manifests.psv`.

Milestone 3 keeps milestones 1–2 behavior and enforces `/app/config/rollout_windows.psv`. Timestamps are 14-digit UTC strings. Manifest `applied_ts` and check `check_ts` must both fall inside an open window for the row's `namespace` where window `state` equals `OPEN_ROLLOUT_STATE` from `/app/src/manifest_rules.pli`.

Status must be exactly `CONSISTENT` or `DRIFTED`.
