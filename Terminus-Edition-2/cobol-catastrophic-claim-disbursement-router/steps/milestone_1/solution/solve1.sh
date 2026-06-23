#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORACLE="$(cd "${SCRIPT_DIR}/../../milestone_4/solution" && pwd)/catclaim_router.oracle.cbl"
sed 's/01 WS-STAGE PIC 9 VALUE 4./01 WS-STAGE PIC 9 VALUE 1./' "$ORACLE" > /app/src/catclaim_router.cbl
/app/scripts/run_batch.sh
