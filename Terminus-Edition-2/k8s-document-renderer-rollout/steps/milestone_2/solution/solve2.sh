#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="${APP_ROOT:-/app}"
mkdir -p "$APP_ROOT/src" "$APP_ROOT/out" "$APP_ROOT/state"
cat > "$APP_ROOT/src/document_rollout_simulator.py" <<'PYCODE'
#!/usr/bin/env python3
import argparse, json, os, pathlib, hashlib, copy
ROOT = pathlib.Path(os.environ.get("TASK_ROOT", "/app"))
ROLLOUT_CONTRACT_CHECKS = True
AUTHORIZATION_POLICY_CHECKS = True
QUEUE_LEDGER_CHECKS = False
SEQUENCING_FAILOVER_CHECKS = False
reported_level = 2
TASK_NAME = 'k8s-document-renderer-rollout'

def load_json(path, default):
    p = ROOT / path
    if not p.exists():
        return copy.deepcopy(default)
    with p.open() as f:
        return json.load(f)

def write_json(path, obj):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w') as f:
        json.dump(obj, f, indent=2, sort_keys=True)

def stable_hash(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()[:12]

def decision_for(case):
    # The simulator intentionally uses the contract data in the fixture rather than hidden expected output.
    req = case.get('request', {})
    policy = case.get('policy', {})
    out = {'case': case['id'], 'status': 'ALLOW', 'reason': 'OK', 'selected': req.get('preferred') or req.get('id') or case['id'], 'audit': []}
    # M1: identity / mapping / layout / selector / artifact contract checks.
    if not ROLLOUT_CONTRACT_CHECKS:
        out.update(status='ALLOW', reason='LEGACY_FALLBACK')
        return out
    for key, expected in policy.get('must_equal', {}).items():
        if req.get(key) != expected:
            return {**out, 'status':'DENY', 'reason': policy.get('reason_'+key, 'CONTRACT_MISMATCH'), 'selected': None}
    for key, forbidden in policy.get('must_not_equal', {}).items():
        if req.get(key) == forbidden:
            return {**out, 'status':'DENY', 'reason': policy.get('reason_'+key, 'FORBIDDEN_VALUE'), 'selected': None}
    if policy.get('enabled') is False:
        return {**out, 'status':'DENY', 'reason':'DISABLED_CONTRACT', 'selected': None}
    if policy.get('schema_required'):
        missing=[k for k in policy['schema_required'] if k not in req]
        if missing:
            return {**out, 'status':'DENY', 'reason':'SCHEMA_MISSING', 'selected': None, 'missing': missing}
    # M2: authorization / trust / restart / probes / isolation policy checks.
    if AUTHORIZATION_POLICY_CHECKS:
        for key, allowed in policy.get('allow_values', {}).items():
            if req.get(key) not in allowed:
                return {**out, 'status':'DENY', 'reason': policy.get('reason_allow_'+key, 'NOT_ALLOWED'), 'selected': None}
        if policy.get('deny_wildcard') and ('*' in str(req.get('resource','')) or req.get('action') == '*'):
            return {**out, 'status':'DENY', 'reason':'WILDCARD_DENIED', 'selected': None}
        if policy.get('requires_owner') and req.get('owner') != req.get('actor'):
            return {**out, 'status':'DENY', 'reason':'OWNER_MISMATCH', 'selected': None}
        if policy.get('health') == 'degraded' and policy.get('liveness_sensitive') is False and req.get('probe') == 'liveness':
            out['reason']='LIVENESS_OK_DEPENDENCY_DEGRADED'
        elif policy.get('health') == 'degraded' and req.get('probe') == 'readiness':
            return {**out, 'status':'DENY', 'reason':'READINESS_BLOCKED', 'selected': None}
    # M3: stateful replay / quality gate / idempotency / cache behavior.
    ledger = load_json('state/ledger.json', {'committed': []})
    committed_keys = set(ledger.get('committed', []))
    key = req.get('id') or req.get('artifact_digest') or req.get('business_id') or stable_hash(req)
    if QUEUE_LEDGER_CHECKS:
        if policy.get('stale_event'):
            return {**out, 'status':'SUPPRESSED', 'reason':'STALE_EVENT', 'selected': None}
        if policy.get('poison'):
            attempts = int(req.get('attempts', 0))
            max_attempts = int(policy.get('max_attempts', 3))
            if attempts >= max_attempts:
                return {**out, 'status':'DLQ', 'reason': policy.get('poison_reason','POISON_MAX_RECEIVES'), 'selected': None}
            return {**out, 'status':'RETRY', 'reason': policy.get('poison_reason','POISON_RETRY'), 'selected': None}
        if key in committed_keys or req.get('duplicate_of') in committed_keys:
            return {**out, 'status':'SUPPRESSED', 'reason':'DUPLICATE_COMMITTED', 'selected': None}
        if policy.get('quality_gate') == 'failed':
            return {**out, 'status':'DENY', 'reason':'QUALITY_GATE_FAILED', 'selected': None}
        if policy.get('quality_gate') == 'mismatch':
            return {**out, 'status':'DENY', 'reason':'QUALITY_GATE_PROVENANCE_MISMATCH', 'selected': None}
        committed_keys.add(key)
        ledger['committed'] = sorted(committed_keys)
        write_json('state/ledger.json', ledger)
    # M4: sequencing / failover / rollout / rollback semantics.
    if SEQUENCING_FAILOVER_CHECKS:
        seq = req.get('seq')
        if policy.get('bad_sequence'):
            return {**out, 'status':'ANOMALY', 'reason':'BAD_SEQUENCE', 'selected': None}
        if policy.get('gap'):
            return {**out, 'status':'ANOMALY', 'reason':'SEQUENCE_GAP', 'detail': policy.get('gap_detail','gap_detected')}
        if policy.get('conflict'):
            return {**out, 'status':'DENY', 'reason': policy.get('conflict_reason','CONFLICT'), 'selected': None}
        if policy.get('fallback'):
            out['selected'] = policy['fallback']
            out['reason'] = 'FAILOVER_SELECTED'
        if policy.get('rollback_digest'):
            out['selected'] = policy['rollback_digest']
            out['reason'] = 'ROLLBACK_FROM_HISTORY'
    return out

def run_suite(suite):
    cases = load_json(f'data/{suite}.json', {'cases': []}).get('cases', [])
    results=[decision_for(c) for c in cases]
    summary={}
    for r in results:
        summary[r['status']] = summary.get(r['status'],0)+1
    return {'task': TASK_NAME, 'level': reported_level, 'suite': suite, 'results': results, 'summary': summary}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--suite', required=True)
    ap.add_argument('--out', default=None)
    args=ap.parse_args()
    result=run_suite(args.suite)
    if args.out:
        write_json(args.out, result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
if __name__ == '__main__':
    main()

PYCODE
chmod +x "$APP_ROOT/src/document_rollout_simulator.py"
