#!/usr/bin/env bash
# Pack all revision tasks (manifest + 3 extra) into revision-custom-upload/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$ROOT/Revision-ChatGpt/needs_revision_pulls/portal_ids_manifest.tsv"
OUT="$ROOT/revision-custom-upload"
RUBRICS="$ROOT/revision-custom-rubrics"
LOG="$ROOT/Revision-ChatGpt/revision_batch_logs/pack_custom_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$OUT" "$RUBRICS" "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

declare -A seen=()
ok=0
fail=0

pack_one() {
  local folder="$1"
  [[ -n "${seen[$folder]:-}" ]] && return 0
  seen[$folder]=1
  local task_dir="$ROOT/$folder"
  if [[ ! -f "$task_dir/task.toml" ]]; then
    echo "FAIL missing $folder"
    ((fail++)) || true
    return 1
  fi
  echo "PACK $folder"
  if bash "$ROOT/scripts/zip.sh" --task "$task_dir" --out "$OUT" --zip-name "${folder}.zip"; then
    [[ -f "$task_dir/rubric.txt" ]] && cp "$task_dir/rubric.txt" "$RUBRICS/${folder}.rubric.txt"
    ((ok++)) || true
  else
    echo "FAIL zip $folder"
    ((fail++)) || true
  fi
}

while IFS=$'\t' read -r _sid folder status; do
  [[ "$status" == "LOCAL_OK" ]] && pack_one "$folder"
done < "$MANIFEST"

for extra in \
  go-conference-sponsor-rebate-matcher \
  cobol-vendor-return-settlement \
  go-marketplace-payout-matcher \
  ruby-courier-cod-remittance-reconciler \
  go-datacenter-rack-hold-release \
  go-property-lease-deposit-reconciler \
  go-childcare-attendance-refund-matcher; do
  pack_one "$extra"
done

echo "=== PACK CUSTOM DONE ok=$ok fail=$fail out=$OUT rubrics=$RUBRICS log=$LOG ==="
