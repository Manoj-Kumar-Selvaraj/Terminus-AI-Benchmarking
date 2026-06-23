#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/lockbox_apply.cbl")
text = path.read_text()
text = text.replace(
    '      10 INV-CHANNEL PIC X(3).',
    '      10 INV-CHANNEL PIC X(3).\n      10 INV-USED PIC X.',
)
text = text.replace(
    '                    MOVE INVOICE-REC(44:1) TO INV-HOLD(WS-INVOICE-COUNT)',
    '                    MOVE INVOICE-REC(44:1) TO INV-HOLD(WS-INVOICE-COUNT)\n                    MOVE "N" TO INV-USED(WS-INVOICE-COUNT)',
)
text = text.replace(
    'SUBTRACT WS-PAY-AMOUNT FROM WS-APPLIED-AMOUNT',
    'ADD WS-PAY-AMOUNT TO WS-APPLIED-AMOUNT\n                        MOVE "Y" TO INV-USED(WS-MATCH-IDX)',
)
text = text.replace(
    'IF INV-ID(WS-IDX)(1:10) = WS-PAY-INVOICE(1:10)',
    'IF INV-USED(WS-IDX) NOT = "Y"\n            AND INV-ID(WS-IDX) = WS-PAY-INVOICE',
)
text = text.replace(
    'AND INV-STATUS(WS-IDX) NOT = "V"',
    'AND INV-STATUS(WS-IDX) = "O"',
)
if 'AND INV-HOLD(WS-IDX) = "N"' not in text:
    text = text.replace(
        'AND INV-STATUS(WS-IDX) = "O"',
        'AND INV-STATUS(WS-IDX) = "O"\n            AND INV-HOLD(WS-IDX) = "N"',
    )
if 'AND WS-PAY-DISPOSITION = "P"' not in text:
    text = text.replace(
        'AND INV-HOLD(WS-IDX) = "N"',
        'AND INV-HOLD(WS-IDX) = "N"\n            AND WS-PAY-DISPOSITION = "P"',
    )
text = text.replace(
    'AND WS-PAY-DATE < INV-CUTOFF-DATE(WS-IDX)',
    'AND WS-PAY-DATE <= INV-CUTOFF-DATE(WS-IDX)',
)
if 'OR INV-CHANNEL(WS-IDX) = "LBX"' not in text:
    text = text.replace(
        'OR INV-CHANNEL(WS-IDX) = "CRD")',
        'OR INV-CHANNEL(WS-IDX) = "CRD"\n                 OR INV-CHANNEL(WS-IDX) = "LBX")',
    )
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/lockbox_report.csv
test -s /app/out/lockbox_summary.txt
