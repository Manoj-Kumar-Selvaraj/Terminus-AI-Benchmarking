#!/usr/bin/env bash
# Submit each batch11 task after oracle pass. Reads batch11_submission_map.txt
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STB="${STB:-/root/.local/bin/stb}"
LOG="$ROOT/.terminus_logs/batch11_submit_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

declare -A IDS
while read -r id folder; do
  [[ -z "$id" || "$id" =~ ^# ]] && continue
  IDS[$folder]=$id
done < batch11_submission_map.txt

while IFS= read -r task; do
  [[ -z "$task" || "$task" =~ ^# ]] && continue
  id="${IDS[$task]:-}"
  if [[ -z "$id" ]]; then
    echo "SKIP $task (no ID)"
    continue
  fi
  echo "=== SUBMIT $task ($id) ==="
  if "$STB" submissions update "$task" -s "$id" --time 90 --no-send-to-reviewer; then
    echo "OK $task"
  else
    echo "FAIL $task"
  fi
  echo
done < batch11_tasks.txt
