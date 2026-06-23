#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
SRC="$ROOT/Revision-ChatGpt/Task-Zip/cobol-db2-financial-master-bulk-update(1).zip"
DST="$ROOT/Revision-ChatGpt/Task-Zip/cobol-db2-financial-master-bulk-update.zip"
cp "$SRC" "$DST"
export TASK_ZIP="$DST"
export SKIP_REPLACE=0
./run_task_revision.sh cobol-db2-financial-master-bulk-update
