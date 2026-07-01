#!/usr/bin/env bash
# Run the cobol-db2-financial-master-bulk-update oracle solution against tests.
set -euo pipefail
TASK="/mnt/d/Manoj/Projects/Portfolio/TerminalBench/Terminus-Edition-2/cobol-db2-financial-master-bulk-update"
IMAGE="local/cobol-db2-finbulk:check"

docker run --rm \
  -v "${TASK}/solution:/solution:ro" \
  -v "${TASK}/tests:/tests:ro" \
  "${IMAGE}" \
  bash -c '
    set -e
    bash /solution/solve.sh
    python3 -m pytest /tests/test_outputs.py -v 2>&1 | tail -80
  '
