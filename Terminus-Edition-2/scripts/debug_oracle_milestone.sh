#!/usr/bin/env bash
set -uo pipefail
ROOT="/mnt/d/Manoj/Projects/Portfolio/TerminalBench/Terminus-Edition-2"
TASK="cobol-campground-site-deposit-matcher"
M="${1:-1}"
docker run --rm -v "$ROOT/$TASK/steps:/steps:ro" "local/$TASK:check" bash -lc "
set -x
bash /steps/milestone_${M}/solution/solve.sh
rm -rf /tests && mkdir -p /tests /logs/verifier
cp -r /steps/milestone_${M}/tests/. /tests/
bash /tests/test.sh || true
cat /logs/verifier/reward.txt
"
