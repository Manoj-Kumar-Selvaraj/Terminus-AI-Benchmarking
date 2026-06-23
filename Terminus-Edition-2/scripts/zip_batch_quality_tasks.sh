#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${1:-batch-quality-hardened-upload}"
mkdir -p "$OUT_DIR"

tasks=(
  aws-lambda-event-source-mapping-recovery
  cobol-catastrophic-claim-disbursement-router
  cobol-retroactive-payroll-adjustment-engine
  k8s-networkpolicy-egress-recovery
  jenkins-release-pipeline-promotion
  k8s-document-renderer-rollout
  cobol-db2-financial-master-bulk-update
  prometheus-edge-gateway-monitoring
  terraform-state-lock-contention
  docker-edge-proxy-deployment-recovery
  docker-compose-cache-backed-api-recovery
)

for t in "${tasks[@]}"; do
  echo "Zipping: $t"
  ./scripts/zip.sh --task "./${t}" --out "$OUT_DIR"
done

echo
echo "ZIP output folder: $ROOT/$OUT_DIR"
ls -la "$OUT_DIR"/*.zip
