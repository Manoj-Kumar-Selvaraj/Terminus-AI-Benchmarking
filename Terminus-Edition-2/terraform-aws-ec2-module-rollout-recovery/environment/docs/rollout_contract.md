# Restart-safe rollout contract

A release change is handled by a fenced `pilot-then-wave` operation.

- `operation_id` is deterministic for application, environment, prior manifest, target manifest, and desired capacity.
- `outputs.rollout_operation_id` mirrors the active refresh `operation_id`. Changing any operation-id input, including desired capacity, must produce a different operation id for a new release operation.
- `owner_token` comes from `rollout.owner_token`; a different owner cannot resume an in-progress operation.
- `instance_refresh` uses `strategy: "pilot-then-wave"`; its `cursor` is the next slot position after durable progress, `completed_slots` is an ascending array of zero-based integer slots, and `min_healthy_percentage` is `ceil((desired_capacity - max_unavailable) * 100 / desired_capacity)`. `max_unavailable` reflects `asg.max_unavailable`.
- At most `asg.max_unavailable` instances may be unavailable at any event.
- The pilot is launched and becomes healthy before its old slot is retired.
- Each later wave launches replacements, records health, and only then retires corresponding old instances.
- Ordered event names are stored in each event object's `event` field, never in a `name` field. The sequence is `pilot_launched`, `pilot_healthy`, `pilot_committed`, followed by one `wave_launched`, `wave_healthy`, `wave_committed` trio for every post-pilot wave group, and finally `rollout_completed`. A wave group contains at most `asg.wave_size` remaining slots. The three events for a group share one `wave` number and the same `slots` array; do not emit one trio per slot. For remaining slots `[1,2,3,4,5]` and `wave_size=2`, emit the trios for `[1,2]`, `[3,4]`, then `[5]`.
- Every event has one-based increasing integer `seq`, integer `healthy_capacity`, and integer `unavailable`. Pilot events additionally carry `slot: 0`; wave events carry integer `wave` and an ordered integer `slots` array. The simulator records zero unavailable and the desired healthy capacity for the safe launch, health, and commit events.
- Failed pilot health uses `pilot_unhealthy` before rollback. Failed wave health uses `wave_unhealthy` before rollback.
- A no-change fleet has `status: "stable"`. Replacement states are `in_progress`, `completed`, or `rolled_back`.
- Failed pilot or wave health produces `rolled_back`, preserves the complete prior fleet, and records `previous_capacity_preserved`.
- `fault_point: after_pilot_commit_response_lost` commits the pilot, atomically writes state and its journal record, sets `status: "in_progress"` with `completed_slots: [0]`, sets `control_plane_response_lost: true`, and exits the `apply` command with status `3`. Re-running without the fault resumes at the first unfinished slot without duplicate identities or events.
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
