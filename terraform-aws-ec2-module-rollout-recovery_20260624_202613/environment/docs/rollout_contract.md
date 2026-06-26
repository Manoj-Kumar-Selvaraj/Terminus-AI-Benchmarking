# Restart-safe rollout contract

A release change is handled by a fenced `pilot-then-wave` operation.

- `operation_id` is deterministic for application, environment, prior manifest, target manifest, and desired capacity.
- `outputs.rollout_operation_id` mirrors the active refresh `operation_id`. Changing any operation-id input, including desired capacity, must produce a different operation id for a new release operation.
- `owner_token` comes from `rollout.owner_token`; a different owner cannot resume an in-progress operation.
- At most `asg.max_unavailable` instances may be unavailable at any event.
- The pilot is launched and becomes healthy before its old slot is retired.
- Each later wave launches replacements, records health, and only then retires corresponding old instances.
- Ordered event names are `pilot_launched`, `pilot_healthy`, `pilot_committed`, followed by one or more `wave_launched`, `wave_healthy`, `wave_committed`, and finally `rollout_completed`.
- Failed pilot or wave health produces `rolled_back`, preserves the complete prior fleet, and records `previous_capacity_preserved`.
- `fault_point: after_pilot_commit_response_lost` commits the pilot and state before returning a simulated lost response. Re-running with that state resumes at the first unfinished slot without duplicate identities or events.
- A target release change during an in-progress operation fails closed.
