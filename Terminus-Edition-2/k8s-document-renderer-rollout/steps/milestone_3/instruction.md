# Milestone 3 — Fix queue lease idempotency and duplicate render suppression

You are recovering `k8s-document-renderer-rollout`, a production-style offline incident task for a Kubernetes document renderer rollout simulator.

## Incident context

Offline Kubernetes rollout for document rendering workers; queue leases, persistent cache, network policy, and rollout safety are checked semantically. Operators report that the visible symptom in this milestone remains unresolved after the previous repair. Several evidence files include unrelated warnings, old observations, and stale incident notes; use them as context, but satisfy the contracts below.

## Evidence to inspect

- `/app/evidence/document_queue_stall.log`
- `/app/evidence/pvc_mount_events.txt`
- `/app/evidence/network_policy_drop_trace.json`
- `/app/evidence/worker_duplicate_render.md`

## Input format

The offline simulator reads JSON suites from `/app/data/milestone_3.json`. Each suite contains a top-level `cases` array. Each case has:

```json
{
  "id": "case identifier",
  "request": { "domain fields": "value" },
  "policy": { "contract fields": "value" }
}
```

Configuration and state are under `/app/config` and `/app/state`. Do not remove or rename these directories. The public command remains:

```bash
python3 /app/src/document_rollout_simulator.py --suite milestone_3
```

## Expected output/result format

The simulator must emit JSON with this shape:

```json
{
  "task": "k8s-document-renderer-rollout",
  "level": 1,
  "suite": "milestone_3",
  "results": [
    {"case":"...", "status":"ALLOW|DENY|SUPPRESSED|RETRY|DLQ|ANOMALY", "reason":"...", "selected":"..."}
  ],
  "summary": {"ALLOW": 1}
}
```

Milestone-specific artifacts must remain compatible:

- `/app/out/document_rollout_report.json`
- `/app/out/render_ledger.json`

## Requirements

1. Use /app/state/render_ledger.json and /app/config/queue_lease_contract.json for offline queue simulation.
2. Renew leases only for the owning worker.
3. Suppress duplicate renders by document id and render version.
4. Move poisoned render jobs to DLQ with stable reason after max attempts.

## Verifier-covered requirements

1. owner can renew lease.
2. non-owner cannot renew lease.
3. duplicate render is suppressed.
4. poison render reaches DLQ with reason.
5. result schema is stable.

## Constraints

- Do not require live cloud, Kubernetes, Jenkins, database, or network access.
- Do not delete fixtures, evidence, or state files to make tests pass.
- Do not replace the simulator with a script that only prints hardcoded expected outputs.
- Do not broaden authorization or routing contracts with wildcards unless the milestone contract explicitly allows it.
- Preserve public command names, output schemas, and state/config file locations.
