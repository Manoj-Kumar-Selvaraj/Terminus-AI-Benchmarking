#!/usr/bin/env bash
set -euo pipefail
cd /app
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
if ! grep -q "OPEN INPUT LEDGER-FILE" /app/src/billing_approval.cbl; then
  bash "$STEPS_ROOT/milestone_2/solution/solve2.sh"
fi
python3 <<'PY'
from pathlib import Path
path = Path("/app/src/billing_approval.cbl")
text = path.read_text()
old = """                       IF WS-APPROVAL-TIER = "DUAL"
                           PERFORM WRITE-TRACE-REGIONAL
                           MOVE "REGIONAL" TO WS-STAGE-TRACE
                           MOVE "APPROVED" TO WS-FINAL-STATUS
                       END-IF"""
new = """                       IF WS-APPROVAL-TIER = "DUAL"
                           PERFORM WRITE-TRACE-REGIONAL
                           PERFORM WRITE-TRACE-FINANCE
                           MOVE "REGIONAL+FIN" TO WS-STAGE-TRACE
                           MOVE "APPROVED" TO WS-FINAL-STATUS
                       END-IF"""
if old not in text:
    raise SystemExit("milestone 3 patch anchor missing")
path.write_text(text.replace(old, new, 1))
# normalize stage label for tests
text = path.read_text()
text = text.replace('MOVE "REGIONAL+FIN" TO WS-STAGE-TRACE', 'MOVE "REGIONAL+FINANCE" TO WS-STAGE-TRACE', 1)
path.write_text(text)
PY
/app/scripts/run_batch.sh
