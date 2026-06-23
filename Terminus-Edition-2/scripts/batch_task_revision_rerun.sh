#!/usr/bin/env bash
# Batch revision workflow for the 10-task fix batch.
# Fixed loop: separate `done` and `echo` (user had `doneecho` typo).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

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

LOG_FILE="${ROOT}/Revision-ChatGpt/batch_revision_rerun_$(date +%Y%m%d_%H%M%S).log"
PASS=0
FAIL=0

{
  echo "Batch revision rerun started: $(date -Iseconds)"
  echo "Log: $LOG_FILE"
  echo

  for task in "${tasks[@]}"; do
    echo "============================================================"
    echo "Running: $task"
    echo "============================================================"

    if SKIP_REPLACE=1 ./run_task_revision.sh "$task"; then
      echo "RESULT: PASS $task"
      PASS=$((PASS + 1))
    else
      echo "RESULT: FAIL $task"
      FAIL=$((FAIL + 1))
    fi

    echo "COMPLETED: $task"
    echo
  done

  echo "============================================================"
  echo "Batch summary: PASS=$PASS FAIL=$FAIL TOTAL=${#tasks[@]}"
  echo "Finished: $(date -Iseconds)"
} 2>&1 | tee "$LOG_FILE"

exit "$FAIL"
