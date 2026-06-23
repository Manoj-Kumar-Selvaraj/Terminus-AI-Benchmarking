#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
task="${1:?task name}"
m="${2:?milestone number}"
taskdir="$ROOT/$task"
image="local/${task}:dbg"

docker build -t "$image" "$taskdir/environment"
docker run --rm -v "$taskdir/steps:/steps:ro" "$image" bash -lc "
  set -e
  mkdir -p /logs/verifier
  bash /steps/milestone_${m}/solution/solve.sh
  rm -rf /tests
  mkdir -p /tests
  cp -r /steps/milestone_${m}/tests/. /tests/
  bash /tests/test.sh
  cat /logs/verifier/reward.txt
"
