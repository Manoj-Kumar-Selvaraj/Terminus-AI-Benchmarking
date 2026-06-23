#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install -q ruff 2>/dev/null || true
TASKS=(
  aws-lambda-event-source-mapping-recovery
  cobol-catastrophic-claim-disbursement-router
  cobol-retroactive-payroll-adjustment-engine
  cobol-db2-financial-master-bulk-update
  k8s-networkpolicy-egress-recovery
  jenkins-release-pipeline-promotion
  k8s-document-renderer-rollout
  prometheus-edge-gateway-monitoring
  terraform-state-lock-contention
  docker-edge-proxy-deployment-recovery
  docker-compose-cache-backed-api-recovery
)
for t in "${TASKS[@]}"; do
  echo "=== $t ==="
  python3 -m ruff check "$t" --select E702
done
echo "ALL_E702_PASS"
