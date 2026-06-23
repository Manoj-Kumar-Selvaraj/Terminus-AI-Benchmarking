#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/Revision-ChatGpt/revision_batch_logs/oracle_all_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

mapfile -t TASKS < <(python3 -c "
import sys
sys.path.insert(0, '$ROOT/scripts')
from fix_custom_revisions_batch import all_tasks
for t in all_tasks():
    print(t)
")

pass=0
fail=0
failed=()
for t in "${TASKS[@]}"; do
  echo "===== ORACLE $t ====="
  if bash "$ROOT/scripts/terminus2_cli.sh" oracle "$ROOT/$t"; then
    ((pass++)) || true
  else
    ((fail++)) || true
    failed+=("$t")
  fi
done
echo "=== ORACLE ALL pass=$pass fail=$fail log=$LOG ==="
if ((${#failed[@]})); then
  echo "FAILED: ${failed[*]}"
fi
