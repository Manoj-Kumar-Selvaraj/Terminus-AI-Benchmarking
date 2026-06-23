#!/usr/bin/env bash
set -euo pipefail

cd /app
python3 <<'PY'
from pathlib import Path
path = Path("/app/src/draft_returns.cbl")
text = path.read_text()

# Re-apply milestone 1 fixes when this oracle is run from a fresh container.
text = text.replace('IF WR-ID(WS-IDX)(1:10) = WS-RETURN-DRAFT(1:10)', 'IF WR-ID(WS-IDX) = WS-RETURN-DRAFT')
if 'OR WR-REASON(WS-IDX) = "B2B")' not in text:
    text = text.replace('OR WR-REASON(WS-IDX) = "ADM")', 'OR WR-REASON(WS-IDX) = "ADM"\n                       OR WR-REASON(WS-IDX) = "B2B")')
text = text.replace('SUBTRACT WS-RETURN-AMOUNT FROM WS-CLEARED-AMOUNT', 'ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT')

# Re-apply milestone 2 consumption fixes when needed.
if '10 WR-USED PIC X.' not in text:
    text = text.replace('             10 WR-STATUS PIC X.', '             10 WR-STATUS PIC X.\n             10 WR-USED PIC X.')
if 'MOVE "N" TO WR-USED(WS-DRAFT-COUNT)' not in text:
    text = text.replace('           MOVE DRAFT-REC(35:1) TO WR-STATUS(WS-DRAFT-COUNT).', '           MOVE DRAFT-REC(35:1) TO WR-STATUS(WS-DRAFT-COUNT)\n           MOVE "N" TO WR-USED(WS-DRAFT-COUNT).')
if 'IF WR-USED(WS-IDX) NOT = "Y"' not in text:
    text = text.replace('IF WR-ID(WS-IDX) = WS-RETURN-DRAFT\n                  AND WR-ACCOUNT', 'IF WR-USED(WS-IDX) NOT = "Y"\n                  AND WR-ID(WS-IDX) = WS-RETURN-DRAFT\n                  AND WR-ACCOUNT')
if 'MOVE "Y" TO WR-USED(WS-MATCH-IDX)' not in text:
    text = text.replace('ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT', 'ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT\n               MOVE "Y" TO WR-USED(WS-MATCH-IDX)')
path.write_text(text)
PY
/app/scripts/run_batch.sh
test -s /app/out/draft_return_report.csv
test -s /app/out/draft_return_summary.txt
