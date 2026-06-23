#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/ach_reconcile.cbl")
text = path.read_text()
if '10 SET-USED PIC X.' not in text:
    text = text.replace(
        '      10 SET-STATUS PIC X.',
        '      10 SET-STATUS PIC X.\n      10 SET-USED PIC X.',
    )
if 'MOVE "N" TO SET-USED(WS-SETTLE-COUNT)' not in text:
    text = text.replace(
        '                    MOVE SETTLE-REC(47:1) TO SET-STATUS(WS-SETTLE-COUNT)',
        '                    MOVE SETTLE-REC(47:1) TO SET-STATUS(WS-SETTLE-COUNT)\n                    MOVE "N" TO SET-USED(WS-SETTLE-COUNT)',
    )
if 'SET-USED(WS-IDX) NOT = "Y"' not in text:
    text = text.replace(
        '        IF SET-TRACE(WS-IDX) = WS-REV-TRACE\n            AND SET-COMPANY(WS-IDX) = WS-REV-COMPANY',
        '        IF SET-USED(WS-IDX) NOT = "Y"\n            AND SET-TRACE(WS-IDX) = WS-REV-TRACE\n            AND SET-COMPANY(WS-IDX) = WS-REV-COMPANY',
    )
if 'MOVE "Y" TO SET-USED(WS-MATCH-IDX)' not in text:
    text = text.replace(
        '                        ADD WS-REV-AMOUNT TO WS-MATCHED-AMOUNT',
        '                        ADD WS-REV-AMOUNT TO WS-MATCHED-AMOUNT\n                        MOVE "Y" TO SET-USED(WS-MATCH-IDX)',
    )
path.write_text(text)
PY

/app/scripts/run_batch.sh
