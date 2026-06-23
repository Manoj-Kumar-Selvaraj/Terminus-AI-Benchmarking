#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
task="${1:?task name}"
taskdir="$ROOT/$task"
image="local/${task}:check"
docker build -t "$image" "$taskdir/environment" >/dev/null
docker run --rm -v "$taskdir/steps:/steps:ro" "$image" bash -lc "
  set -x
  bash /steps/milestone_1/solution/solve.sh || echo SOLVE_FAIL=\$?
  rm -rf /tests && mkdir -p /tests /logs/verifier
  cp -r /steps/milestone_1/tests/. /tests/
  bash /tests/test.sh || echo TEST_FAIL=\$?
  cat /logs/verifier/reward.txt 2>/dev/null || echo NO_REWARD
"
