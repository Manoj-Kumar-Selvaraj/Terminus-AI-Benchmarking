#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STB="${STB:-/root/.local/bin/stb}"
LOG="$ROOT/.terminus_logs/batch11_pipeline_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

declare -A IDS
while read -r id folder; do
  [[ -z "$id" || "$id" =~ ^# ]] && continue
  IDS[$folder]=$id
done < batch11_submission_map.txt

# Already submitted in this revision pass
declare -A DONE=(
  [go-carwash-subscription-rebate-matcher]=1
  [go-lab-sample-chain-reassignment]=1
  [cobol-telehealth-session-credit-clearing]=1
)

while IFS= read -r task; do
  [[ -z "$task" || "$task" =~ ^# ]] && continue
  [[ -n "${DONE[$task]:-}" ]] && { echo "SKIP $task (done)"; continue; }
  id="${IDS[$task]:-}"
  [[ -z "$id" ]] && { echo "SKIP $task (no id)"; continue; }
  echo "===== $task ====="
  olog="$ROOT/.terminus_logs/pipeline_${task}.log"
  if bash "$ROOT/scripts/oracle_cumulative_go.sh" "$task" > "$olog" 2>&1; then
    echo "ORACLE PASS"
    if "$STB" submissions update "$task" -s "$id" --time 90 --no-send-to-reviewer; then
      echo "SUBMIT OK $task"
    else
      echo "SUBMIT FAIL $task"
    fi
  else
    echo "ORACLE FAIL $task"
    tail -30 "$olog"
  fi
  echo
done < batch11_tasks.txt
