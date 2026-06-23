#!/usr/bin/env bash
set -euo pipefail
cd /app

if grep -q "LOAD-CHECKPOINT." /app/src/stmt_merge.cbl; then
  /app/scripts/run_batch.sh
  exit 0
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/stmt_merge.cbl")
text = path.read_text()

if "01 WS-SKIP-MODE PIC X VALUE \"N\"." not in text:
    text = text.replace(
        "       01 WS-DSP PIC Z(10)9.",
        "       01 WS-DSP PIC Z(10)9.\n"
        "       01 WS-RESTART-ACTIVE PIC X VALUE \"N\".\n"
        "       01 WS-PROCESS-RECORD PIC X VALUE \"Y\".\n"
        "       01 WS-CKPT-FILE-NUM PIC 9(2) VALUE 0.\n"
        "       01 WS-CKPT-RECORD-NUM PIC 9(6) VALUE 0.",
        1,
    )

main_old = """           PERFORM LOAD-MANIFEST
           OPEN OUTPUT CTL-FILE
           OPEN OUTPUT SUMMARY-FILE"""

main_new = """           PERFORM LOAD-MANIFEST
           IF WS-RESTART-FLAG = \"Y\"
               PERFORM LOAD-CHECKPOINT
               OPEN EXTEND CTL-FILE
           ELSE
               OPEN OUTPUT CTL-FILE
           END-IF
           OPEN OUTPUT SUMMARY-FILE"""

if main_old in text:
    text = text.replace(main_old, main_new, 1)

process_old = """                   NOT AT END
                       ADD 1 TO WS-FILE-RECORD-NUM
                       PERFORM HANDLE-STATEMENT"""

process_new = """                   NOT AT END
                       ADD 1 TO WS-FILE-RECORD-NUM
                       MOVE \"Y\" TO WS-PROCESS-RECORD
                       IF WS-RESTART-ACTIVE = \"Y\"
                           IF WS-CURRENT-FILE-NUM < WS-CKPT-FILE-NUM
                               MOVE \"N\" TO WS-PROCESS-RECORD
                           END-IF
                           IF WS-CURRENT-FILE-NUM = WS-CKPT-FILE-NUM
                               AND WS-FILE-RECORD-NUM <= WS-CKPT-RECORD-NUM
                               MOVE \"N\" TO WS-PROCESS-RECORD
                           END-IF
                           IF WS-PROCESS-RECORD = \"Y\"
                               MOVE \"N\" TO WS-RESTART-ACTIVE
                           END-IF
                       END-IF
                       IF WS-PROCESS-RECORD = \"Y\"
                           PERFORM HANDLE-STATEMENT
                       END-IF"""

if process_old in text:
    text = text.replace(process_old, process_new, 1)

write_ckpt_old = """           MOVE WS-PENDING-GROUP TO CKPT-PEND-GROUP
           MOVE SPACES TO CKPT-RESERVED
           WRITE WS-CKPT-REC"""

write_ckpt_new = """           MOVE WS-PENDING-GROUP TO CKPT-PEND-GROUP
           MOVE WS-COMMITTED-GROUPS TO CKPT-COMM-GROUPS
           MOVE WS-TOTAL-DEBIT TO CKPT-TOT-DEBIT
           MOVE WS-TOTAL-CREDIT TO CKPT-TOT-CREDIT
           WRITE WS-CKPT-REC"""

if write_ckpt_old in text:
    text = text.replace(write_ckpt_old, write_ckpt_new, 1)
elif "CKPT-COMM-GROUPS" not in text:
    text = text.replace(
        "           MOVE WS-PENDING-GROUP TO CKPT-PEND-GROUP\n           WRITE WS-CKPT-REC",
        write_ckpt_new,
        1,
    )

load_checkpoint = """
       LOAD-CHECKPOINT.
           OPEN INPUT CHECKPOINT-FILE
           READ CHECKPOINT-FILE
               AT END
                   STOP RUN 1
               NOT AT END
                   MOVE CKPT-COMPOSITE TO WS-LAST-COMPOSITE
                   MOVE CKPT-FILE-NUM TO WS-CKPT-FILE-NUM
                   MOVE CKPT-RECORD-NUM TO WS-CKPT-RECORD-NUM
                   MOVE CKPT-ROW-COUNT TO WS-ROW-COUNT
                   MOVE CKPT-PEND-DEBIT TO WS-PENDING-DEBIT
                   MOVE CKPT-PEND-CREDIT TO WS-PENDING-CREDIT
                   MOVE CKPT-PEND-COUNT TO WS-PENDING-COUNT
                   MOVE CKPT-PEND-GROUP TO WS-PENDING-GROUP
                   MOVE CKPT-COMM-GROUPS TO WS-COMMITTED-GROUPS
                   MOVE CKPT-TOT-DEBIT TO WS-TOTAL-DEBIT
                   MOVE CKPT-TOT-CREDIT TO WS-TOTAL-CREDIT
                   MOVE WS-PENDING-GROUP(1:8) TO WS-PENDING-ACCOUNT
                   MOVE WS-PENDING-GROUP(9:8) TO WS-PENDING-DATE
                   MOVE WS-CKPT-FILE-NUM TO WS-CURRENT-FILE-NUM
                   MOVE \"Y\" TO WS-RESTART-ACTIVE
                   MOVE \"Y\" TO WS-LAST-COMPOSITE-FLAG
           END-READ
           CLOSE CHECKPOINT-FILE.
"""

if "LOAD-CHECKPOINT." not in text:
    text = text.replace("       WRITE-SUMMARY.", load_checkpoint + "\n       WRITE-SUMMARY.", 1)

if "AND WS-RESTART-ACTIVE NOT = \"Y\"" not in text:
    text = text.replace(
        "IF WS-CARRY-COMPOSITE-FLAG NOT = \"Y\"",
        "IF WS-CARRY-COMPOSITE-FLAG NOT = \"Y\"\n               AND WS-RESTART-ACTIVE NOT = \"Y\"",
        1,
    )

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/control_totals.dat
test -s /app/out/merge_summary.txt
