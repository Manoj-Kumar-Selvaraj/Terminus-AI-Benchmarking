# Milestone 2 — Recover font/cache PVC and configuration mounts

You are recovering `k8s-document-renderer-rollout`, a production-style offline incident task for a Kubernetes document renderer rollout simulator.

## Incident context

Offline Kubernetes rollout for document rendering workers; queue leases, persistent cache, network policy, and rollout safety are checked semantically. Operators report that the visible symptom in this milestone remains unresolved after the previous repair. Several evidence files include unrelated warnings, old observations, and stale incident notes; use them as context, but satisfy the contracts below.

## Evidence to inspect

- `/app/evidence/document_queue_stall.log`
- `/app/evidence/pvc_mount_events.txt`
- `/app/evidence/network_policy_drop_trace.json`
- `/app/evidence/worker_duplicate_render.md`

## Input format

The offline simulator reads JSON suites from `/app/data/milestone_2.json`. Each suite contains a top-level `cases` array. Each case has:

```json
{
  "id": "case identifier",
  "request": { "domain fields": "value" },
  "policy": { "contract fields": "value" }
}
```

Configuration and state are under `/app/config` and `/app/state`. Do not remove or rename these directories. The public command remains:

```bash
python3 /app/src/document_rollout_simulator.py --suite milestone_2
```

## Expected output/result format

The simulator must emit JSON with this shape:

```json
{
  "task": "k8s-document-renderer-rollout",
  "level": 1,
  "suite": "milestone_2",
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

1. Mount font cache PVC and renderer ConfigMap at documented paths.
2. Do not mount writable secrets into untrusted worker paths.
3. Keep init container cache warming before main renderer start.
4. Preserve cache volume identity during rollout.

## Verifier-covered requirements

1. font cache PVC is mounted.
2. config mount path is present.
3. secret is not writable in worker path.
4. init cache warmer runs first.
5. result schema is stable.

## Constraints

- Do not require live cloud, Kubernetes, Jenkins, database, or network access.
- Do not delete fixtures, evidence, or state files to make tests pass.
- Do not replace the simulator with a script that only prints hardcoded expected outputs.
- Do not broaden authorization or routing contracts with wildcards unless the milestone contract explicitly allows it.
- Preserve public command names, output schemas, and state/config file locations.
