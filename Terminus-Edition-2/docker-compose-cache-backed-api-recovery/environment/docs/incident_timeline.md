# Docker Compose cache-backed API incident

A compose-based API cutover began serving stale cache entries before dependencies were truly healthy, then duplicated writes after restart and corrupted cache during rollback.

- T+00 rollout begins.
- T+07 first symptom appears in downstream state.
- T+19 operator capture shows green checks disagreeing with persisted state.
- T+34 rollback or replay path is attempted and exposes a deeper failure.
