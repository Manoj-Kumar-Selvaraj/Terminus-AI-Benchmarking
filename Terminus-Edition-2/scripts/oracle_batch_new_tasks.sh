#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIST="${1:-$ROOT/new_tasks.txt}"
LOG_DIR="$ROOT/.terminus_logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/oracle_new_tasks_$(date +%Y%m%d_%H%M%S).log"
SUMMARY="$LOG_DIR/oracle_new_tasks_latest_summary.txt"

run_task() {
  local task="$1"
  local taskdir="$ROOT/$task"
  if [[ ! -d "$taskdir" ]]; then
    echo "SKIP $task (directory missing)" | tee -a "$LOG"
    return 2
  fi
  local image="local/${task}:check"
  echo "========== $task ==========" | tee -a "$LOG"
  if ! docker build -t "$image" "$taskdir/environment" >>"$LOG" 2>&1; then
    echo "FAIL $task docker build" | tee -a "$LOG"
    return 1
  fi
  local max_m=3
  if [[ -f "$taskdir/task.toml" ]]; then
    max_m="$(grep -E '^number_of_milestones\s*=' "$taskdir/task.toml" | head -1 | sed -E 's/.*=\s*//')"
    max_m="${max_m//$'\r'/}"
    max_m="${max_m:-3}"
  fi
  if ! [[ "$max_m" =~ ^[0-9]+$ ]] || (( max_m < 1 )); then
    echo "FAIL $task invalid number_of_milestones=$max_m" | tee -a "$LOG"
    return 1
  fi
  local m reward rc ran=0
  for ((m = 1; m <= max_m; m++)); do
    ran=1
    echo "--- $task milestone_$m ---" | tee -a "$LOG"
    reward="$(
      docker run --rm -v "$taskdir/steps:/steps:ro" "$image" bash -lc "
        set -e
        bash /steps/milestone_${m}/solution/solve.sh
        rm -rf /tests && mkdir -p /tests /logs/verifier
        cp -r /steps/milestone_${m}/tests/. /tests/
        bash /tests/test.sh >/tmp/test-stdout.txt 2>/tmp/test-stderr.txt || test_rc=\$?
        cat /logs/verifier/reward.txt
        exit \${test_rc:-0}
      " 2>>"$LOG" | tail -n 1
    )" || rc=$?
    rc="${rc:-0}"
    if [[ "$rc" -ne 0 || "$reward" != "1" ]]; then
      echo "FAIL $task milestone_$m reward=${reward:-empty} rc=$rc" | tee -a "$LOG"
      return 1
    fi
    echo "PASS $task milestone_$m" | tee -a "$LOG"
  done
  if (( ran == 0 )); then
    echo "FAIL $task no milestones executed" | tee -a "$LOG"
    return 1
  fi
  echo "PASS $task ALL" | tee -a "$LOG"
  return 0
}

passed=()
failed=()
skipped=()

while IFS= read -r task || [[ -n "$task" ]]; do
  task="${task//$'\r'/}"
  task="${task//$'\ufeff'/}"
  [[ -z "$task" || "$task" =~ ^# ]] && continue
  if run_task "$task"; then
    passed+=("$task")
  else
    status=$?
    if [[ "$status" -eq 2 ]]; then
      skipped+=("$task")
    else
      failed+=("$task")
    fi
  fi
done < "$LIST"

{
  echo "Oracle batch finished $(date -Iseconds)"
  echo "List: $LIST"
  echo "Log: $LOG"
  echo "Passed (${#passed[@]}): ${passed[*]:-none}"
  echo "Failed (${#failed[@]}): ${failed[*]:-none}"
  echo "Skipped (${#skipped[@]}): ${skipped[*]:-none}"
} | tee "$SUMMARY"

if ((${#failed[@]} > 0)); then
  exit 1
fi
