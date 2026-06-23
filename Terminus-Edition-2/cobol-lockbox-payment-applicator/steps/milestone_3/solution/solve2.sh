#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/lockbox_apply.cbl")
text = path.read_text()

if "PERFORM NORMALIZE-PAYMENT-CHANNEL" not in text:
    text = text.replace(
        "    MOVE PAYMENT-REC(40:3) TO WS-PAY-CHANNEL.\n    MOVE PAYMENT-REC(43:1) TO WS-PAY-DISPOSITION.",
        "    MOVE PAYMENT-REC(40:3) TO WS-PAY-CHANNEL.\n"
        "    MOVE PAYMENT-REC(43:1) TO WS-PAY-DISPOSITION.\n"
        "    PERFORM NORMALIZE-PAYMENT-CHANNEL.",
    )

if "\nNORMALIZE-PAYMENT-CHANNEL.\n" not in text:
    text = text.replace(
        "\nFIND-MATCH.\n",
        '''\nNORMALIZE-PAYMENT-CHANNEL.
    IF WS-PAY-CHANNEL = "LKB"
        MOVE "LBX" TO WS-PAY-CHANNEL
    ELSE
        IF WS-PAY-CHANNEL = "BNK"
            MOVE "ACH" TO WS-PAY-CHANNEL
        ELSE
            IF WS-PAY-CHANNEL = "CCP"
                MOVE "CRD" TO WS-PAY-CHANNEL
            END-IF
        END-IF
    END-IF.

FIND-MATCH.
''',
    )

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/lockbox_report.csv
test -s /app/out/lockbox_summary.txt
