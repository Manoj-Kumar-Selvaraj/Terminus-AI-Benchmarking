#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/claim_rollup.cbl")
text = path.read_text()
text = text.replace(
    'IF CLM-ID(WS-IDX)(1:10) = WS-ADJ-CLAIM(1:10)',
    'IF CLM-ID(WS-IDX) = WS-ADJ-CLAIM',
)
if 'OR CLM-REASON(WS-IDX) = "COB"' not in text:
    text = text.replace(
        'OR CLM-REASON(WS-IDX) = "NEC"\n                       OR CLM-REASON(WS-IDX) = "AUT")',
        'OR CLM-REASON(WS-IDX) = "NEC"\n                       OR CLM-REASON(WS-IDX) = "COB"\n                       OR CLM-REASON(WS-IDX) = "AUT")',
    )
text = text.replace(
    'SUBTRACT WS-ADJ-AMOUNT FROM WS-MATCHED-AMOUNT',
    'ADD WS-ADJ-AMOUNT TO WS-MATCHED-AMOUNT',
)
text = text.replace(
    '             10 CLM-STATUS PIC X.',
    '             10 CLM-STATUS PIC X.\n             10 CLM-USED PIC X.',
)
text = text.replace(
    '           MOVE CLAIM-REC(35:1) TO CLM-STATUS(WS-CLAIM-COUNT).',
    '           MOVE CLAIM-REC(35:1) TO CLM-STATUS(WS-CLAIM-COUNT)\n           MOVE "N" TO CLM-USED(WS-CLAIM-COUNT).',
)
text = text.replace(
    '               IF CLM-ID(WS-IDX) = WS-ADJ-CLAIM\n                  AND CLM-MEMBER(WS-IDX) = WS-ADJ-MEMBER',
    '               IF CLM-USED(WS-IDX) NOT = "Y"\n                  AND CLM-ID(WS-IDX) = WS-ADJ-CLAIM\n                  AND CLM-MEMBER(WS-IDX) = WS-ADJ-MEMBER',
)
text = text.replace(
    '               ADD 1 TO WS-MATCHED-COUNT\n               ADD WS-ADJ-AMOUNT TO WS-MATCHED-AMOUNT',
    '               ADD 1 TO WS-MATCHED-COUNT\n               ADD WS-ADJ-AMOUNT TO WS-MATCHED-AMOUNT\n               MOVE "Y" TO CLM-USED(WS-MATCH-IDX)',
)
path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/denial_report.csv
test -s /app/out/denial_summary.txt
