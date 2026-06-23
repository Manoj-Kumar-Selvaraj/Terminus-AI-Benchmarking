#!/usr/bin/env bash
set -euo pipefail
cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/stmt_merge.cbl")
text = path.read_text()
old = """           IF WS-LAST-ACCOUNT NOT = SPACES
               AND STM-ACCOUNT NOT = WS-LAST-ACCOUNT
               PERFORM COMMIT-PENDING-GROUP
           END-IF"""
new = """           IF WS-PENDING-GROUP NOT = SPACES
               AND STM-GROUP-KEY NOT = WS-PENDING-GROUP
               PERFORM COMMIT-PENDING-GROUP
           END-IF"""
if old not in text:
    raise SystemExit("milestone 1 patch anchor missing")
path.write_text(text.replace(old, new, 1))
PY

/app/scripts/run_batch.sh
test -s /app/out/control_totals.dat
test -s /app/out/merge_summary.txt
