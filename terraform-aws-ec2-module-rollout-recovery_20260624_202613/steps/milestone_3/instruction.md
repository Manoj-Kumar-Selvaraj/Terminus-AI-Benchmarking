# Make the rollout restart-safe and capacity-safe

The first replacement was retired before its pilot was healthy. A later control-plane response was lost after pilot progress had already committed, and the operator retry created duplicate identities.

Preserve milestones 1–2. Use `/app/docs/rollout_contract.md`, `/app/evidence/asg_refresh_capture.json`, and `/app/evidence/lost_response_trace.jsonl`.

## Required behavior

- Release changes use the documented fenced `pilot-then-wave` operation and ordered event contract.
- The healthy-capacity floor and `max_unavailable` invariant hold at every event for any valid desired capacity.
- Pilot or wave health failure rolls back to the exact prior fleet and records that previous capacity was preserved.
- Operation identity is deterministic for source release, target release, environment, application, and desired capacity.
- A lost response after committed pilot progress writes durable `in_progress` state before returning failure.
- Restart resumes from the first unfinished slot without duplicate instance IDs or repeated pilot events.
- A stale owner or a changed target release cannot resume an in-progress operation.
- Replanning a completed target release is a no-op.
- Preserve private placement, security boundaries, and immutable release provenance.

Do not bypass injected failures, delete durable progress, regenerate operation identity, or implement unbounded retries or fixed sleeps.
