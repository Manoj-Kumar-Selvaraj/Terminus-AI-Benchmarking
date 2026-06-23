#!/usr/bin/env bash
set -euo pipefail
cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/stmt_merge.cbl")
text = path.read_text()

if "01 WS-CARRY-COMPOSITE-FLAG PIC X VALUE \"N\"." not in text:
    text = text.replace(
        "       01 WS-PEEK-IDX PIC 9(2) VALUE 0.",
        "       01 WS-PEEK-IDX PIC 9(2) VALUE 0.\n"
        "       01 WS-PEEK-COMPOSITE PIC X(21) VALUE SPACES.\n"
        "       01 WS-CARRY-COMPOSITE-FLAG PIC X VALUE \"N\".",
        1,
    )

open_block = """       OPEN-STREAM.
           MOVE WS-MAN-PATH(WS-MANIFEST-IDX) TO WS-STM-PATH
           MOVE ZERO TO WS-FILE-RECORD-NUM
           MOVE ZERO TO WS-PENDING-DEBIT
           MOVE ZERO TO WS-PENDING-CREDIT
           MOVE ZERO TO WS-PENDING-COUNT
           MOVE SPACES TO WS-PENDING-GROUP
           MOVE SPACES TO WS-PENDING-ACCOUNT
           MOVE SPACES TO WS-PENDING-DATE
           MOVE SPACES TO WS-LAST-COMPOSITE
           MOVE \"N\" TO WS-LAST-COMPOSITE-FLAG
           OPEN INPUT STM-FILE."""

new_open = """       OPEN-STREAM.
           MOVE WS-MAN-PATH(WS-MANIFEST-IDX) TO WS-STM-PATH
           MOVE ZERO TO WS-FILE-RECORD-NUM
           IF WS-CARRY-COMPOSITE-FLAG NOT = \"Y\"
               MOVE ZERO TO WS-PENDING-DEBIT
               MOVE ZERO TO WS-PENDING-CREDIT
               MOVE ZERO TO WS-PENDING-COUNT
               MOVE SPACES TO WS-PENDING-GROUP
               MOVE SPACES TO WS-PENDING-ACCOUNT
               MOVE SPACES TO WS-PENDING-DATE
           END-IF
           MOVE \"N\" TO WS-CARRY-COMPOSITE-FLAG
           OPEN INPUT STM-FILE."""

if open_block in text:
    text = text.replace(open_block, new_open, 1)

transition_old = """       FILE-TRANSITION-FLUSH.
           COMPUTE WS-PEEK-IDX = WS-MANIFEST-IDX + 1
           MOVE WS-MAN-PATH(WS-PEEK-IDX) TO WS-STM-PATH
           OPEN INPUT STM-FILE
           READ STM-FILE
               AT END CONTINUE
               NOT AT END
                   MOVE STM-LINE TO STM-IN-REC
                   MOVE STM-ACCOUNT TO WS-FLUSH-ACCOUNT
                   MOVE STM-STMT-DATE TO WS-FLUSH-DATE
           END-READ
           CLOSE STM-FILE
           IF WS-PENDING-COUNT > 0
               PERFORM COMMIT-PENDING-GROUP
           END-IF."""

transition_new = """       FILE-TRANSITION-FLUSH.
           MOVE SPACES TO WS-PEEK-COMPOSITE
           COMPUTE WS-PEEK-IDX = WS-MANIFEST-IDX + 1
           MOVE WS-MAN-PATH(WS-PEEK-IDX) TO WS-STM-PATH
           OPEN INPUT STM-FILE
           READ STM-FILE
               AT END CONTINUE
               NOT AT END
                   MOVE STM-LINE TO STM-IN-REC
                   STRING STM-ACCOUNT DELIMITED BY SIZE
                       STM-STMT-DATE DELIMITED BY SIZE
                       STM-SEQ DELIMITED BY SIZE
                       INTO WS-PEEK-COMPOSITE
                   END-STRING
           END-READ
           CLOSE STM-FILE
           IF WS-PENDING-COUNT > 0
               IF WS-PEEK-COMPOSITE = WS-LAST-COMPOSITE
                   MOVE \"Y\" TO WS-CARRY-COMPOSITE-FLAG
               ELSE
                   PERFORM COMMIT-PENDING-GROUP
               END-IF
           END-IF."""

if transition_old in text:
    text = text.replace(transition_old, transition_new, 1)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/control_totals.dat
