#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/ach_reconcile.cbl")
text = path.read_text()
text = text.replace(
    'IF SET-TRACE(WS-IDX)(1:14) = WS-REV-TRACE(1:14)',
    'IF SET-TRACE(WS-IDX) = WS-REV-TRACE',
)
if 'OR SET-SEC(WS-IDX) = "WEB"' not in text:
    text = text.replace(
        'OR SET-SEC(WS-IDX) = "TEL")',
        'OR SET-SEC(WS-IDX) = "WEB"\n                 OR SET-SEC(WS-IDX) = "TEL")',
    )
if 'WS-REV-REASON = "R01"' not in text:
    text = text.replace(
        '            AND SET-STATUS(WS-IDX) = "P"\n            AND (SET-SEC(WS-IDX) = "PPD"',
        '            AND SET-STATUS(WS-IDX) = "P"\n            AND (WS-REV-REASON = "R01"\n                 OR WS-REV-REASON = "R02"\n                 OR WS-REV-REASON = "R03"\n                 OR WS-REV-REASON = "R10")\n            AND (SET-SEC(WS-IDX) = "PPD"',
    )
text = text.replace(
    'SUBTRACT WS-REV-AMOUNT FROM WS-MATCHED-AMOUNT',
    'ADD WS-REV-AMOUNT TO WS-MATCHED-AMOUNT',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
