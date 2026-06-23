#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "${SCRIPT_DIR}/catclaim_router.oracle.cbl" /app/src/catclaim_router.cbl
/app/scripts/run_batch.sh
