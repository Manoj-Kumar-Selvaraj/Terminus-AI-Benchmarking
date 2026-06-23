#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app

python3 <<'PY'
from pathlib import Path
path = Path("/app/src/wire_returns.cbl")
text = path.read_text()
if '10 WR-USED PIC X' not in text:
    text = text.replace(
        '             10 WR-STATUS PIC X.',
        '             10 WR-STATUS PIC X.\n             10 WR-USED PIC X.',
    )
if 'MOVE "N" TO WR-USED(WS-WIRE-COUNT)' not in text:
    text = text.replace(
        '           MOVE WIRE-REC(35:1) TO WR-STATUS(WS-WIRE-COUNT).',
        '           MOVE WIRE-REC(35:1) TO WR-STATUS(WS-WIRE-COUNT)\n           MOVE "N" TO WR-USED(WS-WIRE-COUNT).',
    )
if 'IF WR-USED(WS-IDX) NOT = "Y"' not in text:
    text = text.replace(
        'IF WR-ID(WS-IDX) = WS-RETURN-WIRE\n                  AND WR-ACCOUNT',
        'IF WR-USED(WS-IDX) NOT = "Y"\n                  AND WR-ID(WS-IDX) = WS-RETURN-WIRE\n                  AND WR-ACCOUNT',
    )
if 'MOVE "Y" TO WR-USED(WS-MATCH-IDX)' not in text:
    text = text.replace(
        'ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT',
        'ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT\n               MOVE "Y" TO WR-USED(WS-MATCH-IDX)',
    )
path.write_text(text)
PY
/app/scripts/run_batch.sh
test -s /app/out/wire_return_report.csv
test -s /app/out/wire_return_summary.txt
