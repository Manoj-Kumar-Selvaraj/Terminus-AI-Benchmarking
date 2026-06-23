#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/claim_rollup.cbl")
text = path.read_text()

if "PERFORM NORMALIZE-CLAIM-REASON" not in text:
    text = text.replace(
        "           MOVE CLAIM-REC(14:3) TO CLM-REASON(WS-CLAIM-COUNT)",
        "           MOVE CLAIM-REC(14:3) TO CLM-REASON(WS-CLAIM-COUNT)\n"
        "           PERFORM NORMALIZE-CLAIM-REASON",
    )

if "\n       NORMALIZE-CLAIM-REASON.\n" not in text:
    text = text.replace(
        "\n       PROCESS-ADJUSTMENT.\n",
        '''\n       NORMALIZE-CLAIM-REASON.
           IF CLM-REASON(WS-CLAIM-COUNT) = "BIL"
               MOVE "COB" TO CLM-REASON(WS-CLAIM-COUNT)
           ELSE
               IF CLM-REASON(WS-CLAIM-COUNT) = "AUN"
                   MOVE "AUT" TO CLM-REASON(WS-CLAIM-COUNT)
               ELSE
                   IF CLM-REASON(WS-CLAIM-COUNT) = "CLN"
                       MOVE "NEC" TO CLM-REASON(WS-CLAIM-COUNT)
                   END-IF
               END-IF
           END-IF.

       PROCESS-ADJUSTMENT.
''',
    )

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/denial_report.csv
test -s /app/out/denial_summary.txt
