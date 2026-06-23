#!/usr/bin/env bash
# Run preflight + oracle for manual_revision_batch_20260612 tasks.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAP="$ROOT/Revision-ChatGpt/manual_revision_batch_20260612/submission_mapping.tsv"
OUT="$ROOT/revision-manual-batch-20260612/oracle_results.tsv"
CLI="$ROOT/scripts/terminus2_cli.sh"
echo -e "task_folder\tpreflight\toracle" > "$OUT"
ok=0
fail=0
while IFS=$'\t' read -r sid folder; do
  [[ "$sid" == "submission_id" ]] && continue
  [[ -z "$folder" ]] && continue
  echo "=== ORACLE $folder ==="
  pf="FAIL"
  or="FAIL"
  if (cd "$ROOT" && bash "$CLI" preflight "./$folder" 2>&1); then
    pf="PASS"
  fi
  if (cd "$ROOT" && bash "$CLI" oracle "./$folder" 2>&1); then
    or="PASS"
    ((ok++)) || true
  else
    ((fail++)) || true
  fi
  echo -e "${folder}\t${pf}\t${or}" >> "$OUT"
done < "$MAP"
echo "=== ORACLE DONE ok=$ok fail=$fail results=$OUT ==="
