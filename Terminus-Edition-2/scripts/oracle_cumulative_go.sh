#!/usr/bin/env bash
set -euo pipefail

task="${1:?task directory name}"
root="$(cd "$(dirname "$0")/.." && pwd)"
task_dir="${root}/${task}"
toml="${task_dir}/task.toml"
image="local/${task}:check"

milestones="$(python3 - "$toml" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"number_of_milestones\s*=\s*(\d+)", text)
print(match.group(1) if match else "0")
PY
)"

if [ "$milestones" -le 0 ]; then
  echo "ERROR: ${task} has no milestones in task.toml" >&2
  exit 1
fi

docker build -t "${image}" "${task_dir}/environment"

for ((m = 1; m <= milestones; m++)); do
  echo "=== ${task} milestone_${m} ==="
  docker run --rm -v "${task_dir}/steps:/steps:ro" "${image}" bash -lc "
    set -e
    mkdir -p /logs/verifier
    bash /steps/milestone_${m}/solution/solve.sh
    rm -rf /tests
    mkdir -p /tests
    cp -r /steps/milestone_${m}/tests/. /tests/
    bash /tests/test.sh
    cat /logs/verifier/reward.txt
  "
done
