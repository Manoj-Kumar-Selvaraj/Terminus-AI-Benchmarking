# Terraform state lock contention incident

Two release jobs collided during backend migration. A stale saved plan and force-unlock path risked overwriting remote state after a partial apply.

- T+00 rollout begins.
- T+07 first symptom appears in downstream state.
- T+19 operator capture shows green checks disagreeing with persisted state.
- T+34 rollback or replay path is attempted and exposes a deeper failure.
