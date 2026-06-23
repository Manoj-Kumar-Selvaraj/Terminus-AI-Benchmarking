#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path
path = Path("/app/src/wire_returns.cbl")
text = path.read_text()
if 'IF WR-ID(WS-IDX) = WS-RETURN-WIRE' not in text:
    text = text.replace(
        'IF WR-ID(WS-IDX)(1:10) = WS-RETURN-WIRE(1:10)',
        'IF WR-ID(WS-IDX) = WS-RETURN-WIRE',
    )
if 'OR WR-REASON(WS-IDX) = "B2B")' not in text:
    text = text.replace(
        'OR WR-REASON(WS-IDX) = "ADM")',
        'OR WR-REASON(WS-IDX) = "ADM"\n                       OR WR-REASON(WS-IDX) = "B2B")',
    )
if 'SUBTRACT WS-RETURN-AMOUNT FROM WS-CLEARED-AMOUNT' in text:
    text = text.replace(
        'SUBTRACT WS-RETURN-AMOUNT FROM WS-CLEARED-AMOUNT',
        'ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT',
    )
path.write_text(text)
PY
/app/scripts/run_batch.sh
test -s /app/out/wire_return_report.csv
test -s /app/out/wire_return_summary.txt
