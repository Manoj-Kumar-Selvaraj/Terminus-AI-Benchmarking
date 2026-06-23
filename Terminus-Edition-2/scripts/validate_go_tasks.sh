#!/usr/bin/env bash
# Run preflight + cumulative Docker oracle for one or more Go reconciler tasks.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cmd="${1:?usage: validate_go_tasks.sh <preflight|oracle|all> task [task ...]}"

shift
if [ "$#" -lt 1 ]; then
  echo "usage: validate_go_tasks.sh <preflight|oracle|all> task [task ...]" >&2
  exit 1
fi

run_preflight() {
  local task="$1"
  bash "$root/scripts/terminus2_cli.sh" preflight "./$task"
}

run_oracle() {
  local task="$1"
  bash "$root/scripts/oracle_cumulative_go.sh" "$task"
}

failed=0
for task in "$@"; do
  echo "========== $task =========="
  case "$cmd" in
    preflight)
      run_preflight "$task" || failed=$((failed + 1))
      ;;
    oracle)
      run_oracle "$task" || failed=$((failed + 1))
      ;;
    all)
      run_preflight "$task" || failed=$((failed + 1))
      run_oracle "$task" || failed=$((failed + 1))
      ;;
    *)
      echo "unknown command: $cmd" >&2
      exit 1
      ;;
  esac
done

if [ "$failed" -gt 0 ]; then
  echo "[ERROR] $failed task(s) failed" >&2
  exit 1
fi
echo "[OK] all tasks passed ($cmd)"
