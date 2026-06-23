#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="new-task-upload/submit-batch-20260612"
mkdir -p "$OUT/zips" "$OUT/rubrics"

tasks=(
  ruby-go-bash-vineyard-club-shipment-credit-router
  ruby-ski-resort-lift-gate-release
  go-datacenter-rack-hold-release
  go-helicopter-tour-deposit-reconciler
  go-food-truck-rally-voucher-matcher
  pli-hospital-bed-transfer-event-reconciler
  pli-insurance-fnol-reserve-event-processor
  pli-rail-delay-credit-event-router
)

for t in "${tasks[@]}"; do
  echo "=== Zipping $t ==="
  bash scripts/zip.sh --task "./$t" --out "$OUT/zips" --zip-name "${t}.zip"
done

copy_rubric() {
  local task="$1"
  local dest="$OUT/rubrics/${task}.rubric.txt"
  if [ -f "revision-custom-rubrics/${task}.rubric.txt" ]; then
    cp "revision-custom-rubrics/${task}.rubric.txt" "$dest"
  elif [ -f "${task}/rubric.txt" ]; then
    cp "${task}/rubric.txt" "$dest"
  else
    echo "MISSING RUBRIC: $task" >&2
    return 1
  fi
}

for t in "${tasks[@]}"; do
  echo "=== Rubric $t ==="
  copy_rubric "$t"
done

cat > "$OUT/RUBRIC_REFERENCES.txt" <<'EOF'
SUBMIT BATCH — ZIP + RUBRIC REFERENCES
================================================================================
Date: 2026-06-12
Folder: new-task-upload/submit-batch-20260612/

Upload zips from zips/ to Snorkel portal. Paste matching rubrics from rubrics/
into the UI (rubrics are NOT included in zips).

GOOD TASKS (submit candidates from new_tasks triage)
--------------------------------------------------------------------------------
Task                                              Zip                              Rubric (paste in UI)
------------------------------------------------  -------------------------------  ------------------------------------------
ruby-go-bash-vineyard-club-shipment-credit-router zips/ruby-go-bash-vineyard-club-shipment-credit-router.zip  rubrics/ruby-go-bash-vineyard-club-shipment-credit-router.rubric.txt
ruby-ski-resort-lift-gate-release                 zips/ruby-ski-resort-lift-gate-release.zip                  rubrics/ruby-ski-resort-lift-gate-release.rubric.txt
go-datacenter-rack-hold-release                   zips/go-datacenter-rack-hold-release.zip                    rubrics/go-datacenter-rack-hold-release.rubric.txt
go-helicopter-tour-deposit-reconciler             zips/go-helicopter-tour-deposit-reconciler.zip              rubrics/go-helicopter-tour-deposit-reconciler.rubric.txt
go-food-truck-rally-voucher-matcher               zips/go-food-truck-rally-voucher-matcher.zip                rubrics/go-food-truck-rally-voucher-matcher.rubric.txt

PL/I TASKS (revise docker/oracle before portal if not yet verified)
--------------------------------------------------------------------------------
pli-hospital-bed-transfer-event-reconciler        zips/pli-hospital-bed-transfer-event-reconciler.zip         rubrics/pli-hospital-bed-transfer-event-reconciler.rubric.txt
pli-insurance-fnol-reserve-event-processor        zips/pli-insurance-fnol-reserve-event-processor.zip         rubrics/pli-insurance-fnol-reserve-event-processor.rubric.txt
pli-rail-delay-credit-event-router                zips/pli-rail-delay-credit-event-router.zip                 rubrics/pli-rail-delay-credit-event-router.rubric.txt

Notes
  • vineyard + ski + datacenter + helicopter + food-truck: local oracle PASS
  • PL/I tasks: no oracle log yet; python:3.13 final base may need review
  • Submit one task at a time; wait for portal feedback between uploads
EOF

echo "Batch ready at $OUT"
ls -la "$OUT/zips"
ls -la "$OUT/rubrics"
