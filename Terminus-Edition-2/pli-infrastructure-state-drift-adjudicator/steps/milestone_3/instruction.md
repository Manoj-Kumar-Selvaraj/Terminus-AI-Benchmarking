The infrastructure state drift adjudicator aligns scans outside approved audit windows. Fix `/app/src/drift_batch.pli`, `/app/src/drift_rules.pli`, or the batch harness so `/app/data/observed.psv` reconciles against `/app/data/ideal.psv`.

Milestone 3 keeps milestones 1–2 behavior and enforces `/app/config/audit_windows.psv`. Timestamps are 14-digit UTC strings. Ideal `ideal_ts` and scan `scan_ts` must both fall inside an open window for the row's `resource_group` where window `state` equals `OPEN_AUDIT_STATE` from `/app/src/drift_rules.pli`.

Status must be exactly `ALIGNED` or `DRIFTED`.
