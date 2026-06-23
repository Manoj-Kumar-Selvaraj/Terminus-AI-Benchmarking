# Docker edge proxy deployment incident

A proxy rollout appeared successful but promoted a mutable tag, ignored failed route checks, left stale containers on the public port, and rollback rebuilt from HEAD.

- T+00 rollout begins.
- T+07 first symptom appears in downstream state.
- T+19 operator capture shows green checks disagreeing with persisted state.
- T+34 rollback or replay path is attempted and exposes a deeper failure.
