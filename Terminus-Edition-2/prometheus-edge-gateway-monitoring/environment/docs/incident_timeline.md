# Prometheus edge gateway monitoring incident

A gateway migration left dashboards green while route-level failures and stale scrape gaps were hidden by label loss, counter resets, and release-gate drift.

- T+00 rollout begins.
- T+07 first symptom appears in downstream state.
- T+19 operator capture shows green checks disagreeing with persisted state.
- T+34 rollback or replay path is attempted and exposes a deeper failure.
