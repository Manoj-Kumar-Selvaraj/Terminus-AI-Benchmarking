# Restart-safe rollout contract

A release change is handled by a fenced `pilot-then-wave` operation.

- `operation_id` is deterministic for application, environment, prior manifest, target manifest, and desired capacity.
- `outputs.rollout_operation_id` mirrors the active refresh `operation_id`. Changing any operation-id input, including desired capacity, must produce a different operation id for a new release operation.
- `owner_token` comes from `rollout.owner_token`; a different owner cannot resume an in-progress operation.
- At most `asg.max_unavailable` instances may be unavailable at any event.
- The pilot is launched and becomes healthy before its old slot is retired.
- Each later wave launches replacements, records health, and only then retires corresponding old instances.
- Ordered event names are `pilot_launched`, `pilot_healthy`, `pilot_committed`, followed by one or more `wave_launched`, `wave_healthy`, `wave_committed`, and finally `rollout_completed`.
- Failed pilot health uses `pilot_unhealthy` before rollback. Failed wave health uses `wave_unhealthy` before rollback.
- Terminal refresh `status` values are `completed`, `rolled_back`, or `in_progress`. Do not use informal values such as `stable`.
- Failed pilot or wave health produces `rolled_back`, preserves the complete prior fleet, and records `previous_capacity_preserved`.
- `fault_point: after_pilot_commit_response_lost` commits the pilot and state before returning a simulated lost response. Re-running with that state resumes at the first unfinished slot without duplicate identities or events.
- A target release change during an in-progress operation fails closed with an error containing `target release changed`.
- A different `rollout.owner_token` cannot resume an in-progress operation; validation fails with an error containing `stale rollout owner`.

## Rollout simulation hooks

The offline simulator reads optional `rollout` controls from config:

| Field | Values | Effect |
|-------|--------|--------|
| `candidate_health` | `passing` (default), `fail_pilot`, `fail_wave` | Simulates pilot or wave health-check failure during a new release operation |
| `fault_point` | `none` (default), `after_pilot_commit_response_lost` | Simulates a lost control-plane response after pilot commit |
| `owner_token` | string | Fences in-progress operations to one controller identity |

## Health-check rollback semantics

When `candidate_health` is `fail_pilot` on a new release operation:

- `autoscaling_group.instance_refresh.status` is `rolled_back`
- `instances` and `outputs.instance_ids` remain identical to the prior state
- `events` are exactly, in order: `pilot_launched`, `pilot_unhealthy`, `previous_capacity_preserved`
- No replacement instances are committed

When `candidate_health` is `fail_wave` on a new release operation:

- `autoscaling_group.instance_refresh.status` is `rolled_back`
- `instances` and `outputs.instance_ids` remain identical to the prior state
- The pilot completes (`pilot_launched`, `pilot_healthy`, `pilot_committed`), the first wave launches, wave health fails (`wave_unhealthy`), and the final event is `previous_capacity_preserved`
- No replacement fleet is committed beyond the prior capacity
