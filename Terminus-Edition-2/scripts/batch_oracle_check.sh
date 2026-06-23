#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
tasks=(
  cobol-retroactive-payroll-adjustment-engine
  k8s-networkpolicy-egress-recovery
  jenkins-release-pipeline-promotion
  k8s-document-renderer-rollout
  prometheus-edge-gateway-monitoring
  terraform-state-lock-contention
  docker-edge-proxy-deployment-recovery
  docker-compose-cache-backed-api-recovery
)
for t in "${tasks[@]}"; do
  echo "===== ORACLE $t ====="
  if bash scripts/oracle_cumulative_bash.sh "$t" > "/tmp/oracle_${t}.log" 2>&1; then
    echo "PASS $t"
    grep -E "passed|FAILED|===" "/tmp/oracle_${t}.log" | tail -15
  else
    echo "FAIL $t"
    tail -40 "/tmp/oracle_${t}.log"
  fi
  echo
done
