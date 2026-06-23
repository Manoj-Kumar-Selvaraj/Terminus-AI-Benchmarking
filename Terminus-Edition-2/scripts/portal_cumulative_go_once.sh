#!/usr/bin/env bash
set -euo pipefail
task="${1:?task}"
last="${2:?last milestone}"
root="$(cd "$(dirname "$0")/.." && pwd)"
task_dir="${root}/${task}"
image="local/${task}:check"
docker run --rm -v "${task_dir}/steps:/steps:ro" "${image}" bash -lc "
set -e
for m in \$(seq 1 ${last}); do
  bash /steps/milestone_\${m}/solution/solve.sh
done
mkdir -p /logs/verifier
rm -rf /tests
mkdir -p /tests
cp -r /steps/milestone_${last}/tests/. /tests/
bash /tests/test.sh
cat /logs/verifier/reward.txt
"
