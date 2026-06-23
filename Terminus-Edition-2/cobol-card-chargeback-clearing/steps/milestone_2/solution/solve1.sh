#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path
path = Path("/app/src/chargeback_clear.cbl")
text = path.read_text()
text = text.replace('IF SL-ID(WS-IDX)(1:10) = WS-CHGBK-SALE(1:10)', 'IF SL-ID(WS-IDX) = WS-CHGBK-SALE')
text = text.replace('OR SL-REASON(WS-IDX) = "R99")', 'OR SL-REASON(WS-IDX) = "R99"\n                       OR SL-REASON(WS-IDX) = "MRC")')
text = text.replace('SUBTRACT WS-CHGBK-AMOUNT FROM WS-APPLIED-AMOUNT', 'ADD WS-CHGBK-AMOUNT TO WS-APPLIED-AMOUNT')
path.write_text(text)
PY
/app/scripts/run_batch.sh
test -s /app/out/chargeback_report.csv
test -s /app/out/chargeback_summary.txt
