#!/usr/bin/env bash
# Run cumulative oracle for every task in batch11_tasks.txt; log pass/fail per task.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG_DIR="$ROOT/.terminus_logs/batch11_oracle_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"
SUMMARY="$LOG_DIR/summary.txt"
echo "batch11 oracle run $(date -Iseconds)" > "$SUMMARY"

while IFS= read -r task; do
  [[ -z "$task" || "$task" =~ ^# ]] && continue
  if [[ ! -d "$ROOT/$task" ]]; then
    echo "MISSING $task" | tee -a "$SUMMARY"
    continue
  fi
  echo "===== ORACLE $task =====" | tee -a "$SUMMARY"
  log="$LOG_DIR/${task}.log"
  if USE_DIRECT_HARBOR=1 "$ROOT/scripts/terminus2_cli.sh" oracle "./$task" > "$log" 2>&1; then
    if grep -qE '=== '"$task"' milestone_[0-9]+ ===' "$log" && \
       ! grep -qE '^0$' "$log" | head -1; then
      # check last reward lines per milestone
      fails=0
      while read -r m; do
        [[ -z "$m" ]] && continue
        if ! grep -A1 "=== $task milestone_${m} ===" "$log" | tail -1 | grep -q '^1$'; then
          fails=$((fails+1))
        fi
      done < <(grep -oE 'milestone_[0-9]+' "$log" | sed 's/milestone_//' | sort -u)
      if [[ "$fails" -eq 0 ]]; then
        echo "PASS $task" | tee -a "$SUMMARY"
      else
        echo "FAIL $task (reward)" | tee -a "$SUMMARY"
      fi
    else
      echo "PASS $task" | tee -a "$SUMMARY"
    fi
  else
    echo "FAIL $task (exit)" | tee -a "$SUMMARY"
  fi
done < batch11_tasks.txt

echo "Done. Summary: $SUMMARY"
