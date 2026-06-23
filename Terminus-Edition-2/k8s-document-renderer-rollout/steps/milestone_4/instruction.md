# Milestone 4 — Enforce rollout, PDB, HPA, and network policy safety

You are recovering `k8s-document-renderer-rollout`, a production-style offline incident task for a Kubernetes document renderer rollout simulator.

## Incident context

Offline Kubernetes rollout for document rendering workers; queue leases, persistent cache, network policy, and rollout safety are checked semantically. Operators report that the visible symptom in this milestone remains unresolved after the previous repair. Several evidence files include unrelated warnings, old observations, and stale incident notes; use them as context, but satisfy the contracts below.

## Evidence to inspect

- `/app/evidence/document_queue_stall.log`
- `/app/evidence/pvc_mount_events.txt`
- `/app/evidence/network_policy_drop_trace.json`
- `/app/evidence/worker_duplicate_render.md`

## Input format

The offline simulator reads JSON suites from `/app/data/milestone_4.json`. Each suite contains a top-level `cases` array. Each case has:

```json
{
  "id": "case identifier",
  "request": { "domain fields": "value" },
  "policy": { "contract fields": "value" }
}
```

Configuration and state are under `/app/config` and `/app/state`. Do not remove or rename these directories. The public command remains:

```bash
python3 /app/src/document_rollout_simulator.py --suite milestone_4
```

## Expected output/result format

The simulator must emit JSON with this shape:

```json
{
  "task": "k8s-document-renderer-rollout",
  "level": 1,
  "suite": "milestone_4",
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

1. Keep rolling update availability for API and worker deployments.
2. Configure PDBs to preserve at least one available replica for each tier.
3. Configure HPA bounds using documented CPU and queue metrics.
4. Restrict network policy to required ingress and egress only.

## Verifier-covered requirements

1. rolling update keeps availability.
2. PDB protects API and workers.
3. HPA metrics and bounds are valid.
4. network policy denies unrelated egress.
5. result schema is stable.

## Constraints

- Do not require live cloud, Kubernetes, Jenkins, database, or network access.
- Do not delete fixtures, evidence, or state files to make tests pass.
- Do not replace the simulator with a script that only prints hardcoded expected outputs.
- Do not broaden authorization or routing contracts with wildcards unless the milestone contract explicitly allows it.
- Preserve public command names, output schemas, and state/config file locations.
