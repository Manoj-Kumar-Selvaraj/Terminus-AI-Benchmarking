#!/usr/bin/env bash
set -euo pipefail
cd /app
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
if ! grep -q 'MOVE "REGIONAL+FINANCE" TO WS-STAGE-TRACE' /app/src/billing_approval.cbl; then
  bash "$STEPS_ROOT/milestone_3/solution/solve3.sh"
fi
python3 <<'PY'
from pathlib import Path

path = Path("/app/src/billing_approval.cbl")
text = path.read_text()

old = """               MOVE WS-MAN-IDX TO WS-CURRENT-FILE-NUM
               MOVE WS-MAN-ENTRY(WS-MAN-IDX) TO WS-USG-PATH"""
new = """               MOVE WS-MAN-IDX TO WS-CURRENT-FILE-NUM
               MOVE ZERO TO WS-FILE-RECORD-NUM
               MOVE WS-MAN-ENTRY(WS-MAN-IDX) TO WS-USG-PATH"""
if old not in text:
    raise SystemExit("milestone 4 file cursor anchor missing")
text = text.replace(old, new, 1)

start = text.index("       WRITE-CHECKPOINT.")
end = text.index("       WRITE-SUMMARY.")
new_checkpoint = """       WRITE-CHECKPOINT.
           OPEN OUTPUT CHECKPOINT-FILE
           MOVE SPACES TO WS-CKPT-REC
           MOVE WS-CURRENT-FILE-NUM TO WS-CKPT-REC(1:2)
           MOVE WS-FILE-RECORD-NUM TO WS-CKPT-REC(3:6)
           MOVE WS-CURRENT-ACCOUNT TO WS-CKPT-REC(9:8)
           MOVE WS-ACCOUNT-TOTAL TO WS-CKPT-REC(17:10)
           MOVE WS-USAGE-COUNT TO WS-CKPT-REC(27:6)
           MOVE WS-INVOICE-COUNTER TO WS-CKPT-REC(33:10)
           MOVE WS-ROW-COUNT TO WS-CKPT-REC(43:6)
           MOVE WS-TOTAL-USAGE-ROWS TO WS-CKPT-REC(49:6)
           MOVE WS-INVOICES-POSTED TO WS-CKPT-REC(55:6)
           MOVE WS-TOTAL-BILLED TO WS-CKPT-REC(61:12)
           MOVE WS-DUP-BLOCKED TO WS-CKPT-REC(73:6)
           MOVE WS-BATCH-COUNT TO WS-CKPT-REC(79:2)
           MOVE WS-LAST-LINE-AMOUNT TO WS-CKPT-REC(81:10)
           MOVE WS-BATCH-ENTRY(1) TO WS-CKPT-REC(91:6)
           MOVE WS-BATCH-ENTRY(2) TO WS-CKPT-REC(97:6)
           MOVE WS-BATCH-ENTRY(3) TO WS-CKPT-REC(103:6)
           MOVE WS-BATCH-ENTRY(4) TO WS-CKPT-REC(109:6)
           MOVE WS-BATCH-ENTRY(5) TO WS-CKPT-REC(115:6)
           MOVE WS-BATCH-ENTRY(6) TO WS-CKPT-REC(121:6)
           MOVE WS-BATCH-ENTRY(7) TO WS-CKPT-REC(127:6)
           MOVE WS-BATCH-ENTRY(8) TO WS-CKPT-REC(133:6)
           WRITE WS-CKPT-REC
           CLOSE CHECKPOINT-FILE
           ADD 1 TO WS-CHECKPOINT-COMMITS.

       LOAD-CHECKPOINT.
           OPEN INPUT CHECKPOINT-FILE
           READ CHECKPOINT-FILE
               AT END MOVE "N" TO WS-RESTART-FLAG
               NOT AT END
                   PERFORM PARSE-CHECKPOINT-LINE
                   MOVE "Y" TO WS-RESTART-ACTIVE
           END-READ
           CLOSE CHECKPOINT-FILE.

       PARSE-CHECKPOINT-LINE.
           MOVE WS-CKPT-REC(1:2) TO WS-CKPT-FILE-NUM
           MOVE WS-CKPT-REC(3:6) TO WS-CKPT-RECORD-NUM
           MOVE WS-CKPT-REC(9:8) TO WS-CURRENT-ACCOUNT
           MOVE WS-CKPT-REC(17:10) TO WS-ACCOUNT-TOTAL
           MOVE WS-CKPT-REC(27:6) TO WS-USAGE-COUNT
           MOVE WS-CKPT-REC(33:10) TO WS-INVOICE-COUNTER
           MOVE WS-CKPT-REC(43:6) TO WS-ROW-COUNT
           MOVE WS-CKPT-REC(49:6) TO WS-TOTAL-USAGE-ROWS
           MOVE WS-CKPT-REC(55:6) TO WS-INVOICES-POSTED
           MOVE WS-CKPT-REC(61:12) TO WS-TOTAL-BILLED
           MOVE WS-CKPT-REC(73:6) TO WS-DUP-BLOCKED
           MOVE WS-CKPT-REC(79:2) TO WS-BATCH-COUNT
           MOVE WS-CKPT-REC(81:10) TO WS-LAST-LINE-AMOUNT
           MOVE WS-CKPT-REC(91:6) TO WS-BATCH-ENTRY(1)
           MOVE WS-CKPT-REC(97:6) TO WS-BATCH-ENTRY(2)
           MOVE WS-CKPT-REC(103:6) TO WS-BATCH-ENTRY(3)
           MOVE WS-CKPT-REC(109:6) TO WS-BATCH-ENTRY(4)
           MOVE WS-CKPT-REC(115:6) TO WS-BATCH-ENTRY(5)
           MOVE WS-CKPT-REC(121:6) TO WS-BATCH-ENTRY(6)
           MOVE WS-CKPT-REC(127:6) TO WS-BATCH-ENTRY(7)
           MOVE WS-CKPT-REC(133:6) TO WS-BATCH-ENTRY(8)
           .

"""
text = text[:start] + new_checkpoint + text[end:]

path.write_text(text)
PY
/app/scripts/run_batch.sh
