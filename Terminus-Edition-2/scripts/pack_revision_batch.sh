#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/zip.sh --task ./go-circulation-desk-waiver-reconciler --out revision-custom-upload --zip-name go-circulation-desk-waiver-reconciler.zip
for t in pli-hospital-bed-transfer-event-reconciler pli-insurance-fnol-reserve-event-processor pli-rail-delay-credit-event-router; do
  cp "$t/rubric.txt" "revision-custom-rubrics/${t}.rubric.txt"
  bash scripts/zip.sh --task "./$t" --out revision-custom-upload --zip-name "${t}.zip"
  bash scripts/zip.sh --task "./$t" --out new-task-upload/submit-batch-20260612/zips --zip-name "${t}.zip"
done
echo "Packed:"
ls -la revision-custom-upload/go-circulation-desk-waiver-reconciler.zip revision-custom-upload/pli-*.zip
