#!/usr/bin/env bash
# Pack rubrics + zips for manual_revision_batch_20260612 tasks.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAP="$ROOT/Revision-ChatGpt/manual_revision_batch_20260612/submission_mapping.tsv"
OUT="$ROOT/revision-manual-batch-20260612"
ZIP_DIR="$OUT/zips"
RUB_DIR="$OUT/rubrics"
LOG="$OUT/pack_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$ZIP_DIR" "$RUB_DIR"
exec > >(tee -a "$LOG") 2>&1

ok=0
fail=0
skip=1

while IFS=$'\t' read -r sid folder; do
  [[ "$sid" == "submission_id" ]] && continue
  [[ -z "$folder" ]] && continue
  task_dir="$ROOT/$folder"
  if [[ ! -f "$task_dir/task.toml" ]]; then
    echo "FAIL missing task: $folder ($sid)"
    ((fail++)) || true
    continue
  fi
  echo "=== $folder ($sid) ==="
  # sync rubric to revision-custom-rubrics if task copy exists
  if [[ -f "$task_dir/rubric.txt" ]]; then
    mkdir -p "$ROOT/revision-custom-rubrics"
    cp -f "$task_dir/rubric.txt" "$ROOT/revision-custom-rubrics/${folder}.rubric.txt"
  fi
  rub_src="$ROOT/revision-custom-rubrics/${folder}.rubric.txt"
  if [[ -f "$rub_src" ]]; then
    cp -f "$rub_src" "$RUB_DIR/${folder}.rubric.txt"
    echo "  rubric OK"
  else
    echo "  WARN no rubric for $folder"
  fi
  rm -f "$ZIP_DIR/${folder}.zip"
  if (cd "$ROOT" && sed 's/\r$//' scripts/zip_task.sh | bash -s -- \
      --task "$folder" \
      --out "$ZIP_DIR" \
      --zip-name "${folder}.zip"); then
    echo "  zip OK"
    ((ok++)) || true
  else
    echo "  zip FAIL"
    ((fail++)) || true
  fi
done < "$MAP"

echo "=== PACK DONE ok=$ok fail=$fail out=$OUT log=$LOG ==="
