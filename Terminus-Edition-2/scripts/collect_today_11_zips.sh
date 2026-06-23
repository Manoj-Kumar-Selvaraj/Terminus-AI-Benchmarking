#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/brand-new-task-zips"

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

find_newest_zip() {
  local task="$1"
  local best="" best_mtime=0 mtime zip
  for dir in \
    "${ROOT}/All-revision-new" \
    "${ROOT}/batch-quality-hardened-upload" \
    "${ROOT}/new-task-upload" \
    "${ROOT}/submission_zips"; do
    [[ -d "$dir" ]] || continue
    shopt -s nullglob
    for zip in "${dir}/${task}.zip" "${dir}/${task}"_*.zip; do
      [[ -f "$zip" ]] || continue
      mtime=$(stat -c %Y "$zip")
      if (( mtime > best_mtime )); then
        best_mtime=$mtime
        best=$zip
      fi
    done
    shopt -u nullglob
  done
  printf '%s' "$best"
}

rm -rf "${OUT}"
mkdir -p "${OUT}/zips" "${OUT}/rubrics"

{
  echo "# Today's 11 batch task packages"
  echo ""
  echo "Generated: $(date -u +%Y-%m-%dT%H:%MZ)"
  echo ""
  echo "| # | Task | Zip | Rubric |"
  echo "|---|------|-----|--------|"
} > "${OUT}/MANIFEST.md"

n=0
for task in "${TASKS[@]}"; do
  n=$((n + 1))
  zip=$(find_newest_zip "$task")
  if [[ -z "$zip" ]]; then
    echo "MISSING $task" >&2
    exit 1
  fi
  base=$(basename "$zip")
  cp "$zip" "${OUT}/zips/${base}"
  if [[ -f "${ROOT}/new-task-rubrics/${task}.rubric.txt" ]]; then
    cp "${ROOT}/new-task-rubrics/${task}.rubric.txt" "${OUT}/rubrics/${task}.rubric.txt"
    rub="rubrics/${task}.rubric.txt"
  elif [[ -f "${ROOT}/${task}/rubric.txt" ]]; then
    cp "${ROOT}/${task}/rubric.txt" "${OUT}/rubrics/${task}.rubric.txt"
    rub="rubrics/${task}.rubric.txt"
  else
    rub="(missing)"
  fi
  echo "OK  $task <- $base"
  echo "| ${n} | \`${task}\` | \`zips/${base}\` | \`${rub}\` |" >> "${OUT}/MANIFEST.md"
done

echo "---"
echo "Folder: ${OUT}"
echo "Zips:   $(ls -1 "${OUT}/zips" | wc -l)"
