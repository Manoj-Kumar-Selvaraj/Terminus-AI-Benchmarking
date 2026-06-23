#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd "$(dirname "$0")" && pwd)"
docker run --rm \
  -v "${TASK_DIR}/steps/milestone_1/solution/FNBULKUP_m1.cbl:/app/src/FNBULKUP.cbl:ro" \
  -v "${TASK_DIR}/_test_work:/tmp/work" \
  local/cobol-db2-financial-master-bulk-update:check \
  bash -lc '
    set -euo pipefail
    mkdir -p /tmp/work/out /app/build
    cobc -x -free -O2 -I /app/src/copybooks -o /app/build/FNBULKUP /app/src/FNBULKUP.cbl
    cp /app/data/master_seed.json /tmp/work/db.json
    printf "%s\n" \
      "HT1MISS100 20260618VERIFY  " \
      "D000001AC1000000001 BAL+0000000001250GRP001M1A00001" \
      "D000002ACMISSING001 BAL+0000000000999GRP001M1A00002" \
      "D000003AC1000000002 RAT+0000000000425GRP002M1A00003" \
      "TT1MISS100 000003+0000000001250" \
      > /tmp/work/batch.fb
    export FINBULK_INPUT=/tmp/work/batch.fb
    export FINBULK_DB=/tmp/work/db.json
    export FINBULK_OUT=/tmp/work/out
    export FINBULK_BATCH=T1MISS100
    /app/build/FNBULKUP
    echo exit=$?
    ls -la /tmp/work/out/
    cat /tmp/work/out/summary_T1MISS100.json 2>/dev/null || true
  '
