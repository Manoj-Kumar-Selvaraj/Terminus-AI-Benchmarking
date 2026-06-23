#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/wire_returns.cbl")
text = path.read_text()

if 'CALENDAR-FILE' not in text:
    text = text.replace(
        '           SELECT RETURN-FILE ASSIGN TO "/app/data/returns.dat"\n               ORGANIZATION IS LINE SEQUENTIAL.',
        '           SELECT RETURN-FILE ASSIGN TO "/app/data/returns.dat"\n               ORGANIZATION IS LINE SEQUENTIAL.\n           SELECT CALENDAR-FILE ASSIGN TO "/app/config/cycle_calendar.txt"\n               ORGANIZATION IS LINE SEQUENTIAL.',
    )
    text = text.replace(
        '       FD RETURN-FILE.\n       01 RETURN-REC PIC X(64).',
        '       FD RETURN-FILE.\n       01 RETURN-REC PIC X(64).\n       FD CALENDAR-FILE.\n       01 CALENDAR-REC PIC X(16).',
    )

if 'WS-EOF-CALENDAR' not in text:
    text = text.replace(
        '       01 WS-EOF-RETURN PIC X VALUE "N".',
        '       01 WS-EOF-RETURN PIC X VALUE "N".\n       01 WS-EOF-CALENDAR PIC X VALUE "N".',
    )

if 'WS-CAL-IDX' not in text:
    text = text.replace(
        '       01 WS-IDX PIC 9(4) COMP VALUE 0.',
        '       01 WS-IDX PIC 9(4) COMP VALUE 0.\n       01 WS-CAL-IDX PIC 9(4) COMP VALUE 0.\n       01 WS-CAL-COUNT PIC 9(4) COMP VALUE 0.\n       01 WS-CYCLE-DAYS PIC 9(4) VALUE 0.\n       01 WS-TARGET-DATE PIC X(8).\n       01 WS-DATE-OPEN PIC X VALUE "N".\n       01 WS-WIRE-DATE-OPEN PIC X VALUE "N".\n       01 WS-RETURN-DATE-OPEN PIC X VALUE "N".',
    )

if 'WS-RETURN-DATE PIC X(8)' not in text:
    text = text.replace(
        '       01 WS-RETURN-ACCOUNT PIC X(8).',
        '       01 WS-RETURN-ACCOUNT PIC X(8).\n       01 WS-RETURN-DATE PIC X(8).',
    )

if 'WR-DATE PIC X(8)' not in text:
    if '10 WR-USED PIC X' in text:
        text = text.replace(
            '             10 WR-STATUS PIC X.\n             10 WR-USED PIC X.',
            '             10 WR-STATUS PIC X.\n             10 WR-USED PIC X.\n             10 WR-DATE PIC X(8).',
        )
    else:
        text = text.replace(
            '             10 WR-STATUS PIC X.',
            '             10 WR-STATUS PIC X.\n             10 WR-DATE PIC X(8).',
        )

if 'CALENDAR-TABLE' not in text:
    text = text.replace(
        '       PROCEDURE DIVISION.',
        '       01 CALENDAR-TABLE.\n          05 CAL-ENTRY OCCURS 100 TIMES.\n             10 CAL-DATE PIC X(8).\n             10 CAL-OPEN PIC X.\n\n       PROCEDURE DIVISION.',
    )

if 'PERFORM LOAD-CALENDAR' not in text:
    text = text.replace(
        '       MAIN-PARA.\n           OPEN INPUT WIRE-FILE',
        '       MAIN-PARA.\n           PERFORM LOAD-CALENDAR\n           OPEN INPUT WIRE-FILE',
    )

if 'LOAD-CALENDAR.' not in text:
    text = text.replace(
        '       STORE-WIRE.',
        '''       LOAD-CALENDAR.
           OPEN INPUT CALENDAR-FILE
           PERFORM UNTIL WS-EOF-CALENDAR = "Y"
               READ CALENDAR-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-CALENDAR
                   NOT AT END
                       IF CALENDAR-REC(1:8) NOT = SPACES
                           ADD 1 TO WS-CAL-COUNT
                           MOVE CALENDAR-REC(1:8) TO CAL-DATE(WS-CAL-COUNT)
                           IF FUNCTION UPPER-CASE(CALENDAR-REC(10:4))
                              = "OPEN"
                               MOVE "Y" TO CAL-OPEN(WS-CAL-COUNT)
                           ELSE
                               MOVE "N" TO CAL-OPEN(WS-CAL-COUNT)
                           END-IF
                       END-IF
               END-READ
           END-PERFORM
           CLOSE CALENDAR-FILE.

       STORE-WIRE.''',
    )

if 'MOVE WIRE-REC(36:8) TO WR-DATE' not in text:
    if 'MOVE "N" TO WR-USED(WS-WIRE-COUNT)' in text:
        text = text.replace(
            '           MOVE WIRE-REC(35:1) TO WR-STATUS(WS-WIRE-COUNT)\n           MOVE "N" TO WR-USED(WS-WIRE-COUNT).',
            '           MOVE WIRE-REC(35:1) TO WR-STATUS(WS-WIRE-COUNT)\n           MOVE "N" TO WR-USED(WS-WIRE-COUNT)\n           MOVE WIRE-REC(36:8) TO WR-DATE(WS-WIRE-COUNT).',
        )
    else:
        text = text.replace(
            '           MOVE WIRE-REC(35:1) TO WR-STATUS(WS-WIRE-COUNT).',
            '           MOVE WIRE-REC(35:1) TO WR-STATUS(WS-WIRE-COUNT)\n           MOVE WIRE-REC(36:8) TO WR-DATE(WS-WIRE-COUNT).',
        )

if 'MOVE RETURN-REC(32:8) TO WS-RETURN-DATE' not in text:
    text = text.replace(
        '           MOVE RETURN-REC(24:8) TO WS-RETURN-ACCOUNT',
        '           MOVE RETURN-REC(24:8) TO WS-RETURN-ACCOUNT\n           MOVE RETURN-REC(32:8) TO WS-RETURN-DATE',
    )

if 'PERFORM COUNT-CYCLE-DAYS' not in text:
    start = text.index('           PERFORM VARYING WS-IDX FROM 1 BY 1')
    end = text.index('\n\n           IF WS-MATCH-IDX > 0', start)
    text = text[:start] + '''           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > WS-WIRE-COUNT
               MOVE WR-DATE(WS-IDX) TO WS-TARGET-DATE
               PERFORM CHECK-DATE-OPEN
               MOVE WS-DATE-OPEN TO WS-WIRE-DATE-OPEN
               MOVE WS-RETURN-DATE TO WS-TARGET-DATE
               PERFORM CHECK-DATE-OPEN
               MOVE WS-DATE-OPEN TO WS-RETURN-DATE-OPEN
               PERFORM COUNT-CYCLE-DAYS
               IF WR-USED(WS-IDX) NOT = "Y"
                  AND WS-WIRE-DATE-OPEN = "Y"
                  AND WS-RETURN-DATE-OPEN = "Y"
                  AND WS-RETURN-DATE >= WR-DATE(WS-IDX)
                  AND WS-CYCLE-DAYS <= 2
                  AND WR-ID(WS-IDX) = WS-RETURN-WIRE
                  AND WR-ACCOUNT(WS-IDX) = WS-RETURN-ACCOUNT
                  AND WR-AMOUNT(WS-IDX) = WS-RETURN-AMOUNT
                  AND WR-STATUS(WS-IDX) = "S"
                  AND (WR-REASON(WS-IDX) = "CON"
                       OR WR-REASON(WS-IDX) = "REF"
                       OR WR-REASON(WS-IDX) = "ADM"
                       OR WR-REASON(WS-IDX) = "B2B")
                   IF WS-MATCH-IDX = 0
                       MOVE WS-IDX TO WS-MATCH-IDX
                   ELSE
                       IF WR-DATE(WS-IDX) > WR-DATE(WS-MATCH-IDX)
                           MOVE WS-IDX TO WS-MATCH-IDX
                       END-IF
                   END-IF
               END-IF
           END-PERFORM''' + text[end:]

if 'CHECK-DATE-OPEN.' not in text:
    insert_at = text.index('       WRITE-REPORT-ROW.')
    text = text[:insert_at] + '''       CHECK-DATE-OPEN.
           MOVE "N" TO WS-DATE-OPEN
           PERFORM VARYING WS-CAL-IDX FROM 1 BY 1
               UNTIL WS-CAL-IDX > WS-CAL-COUNT
               IF CAL-DATE(WS-CAL-IDX) = WS-TARGET-DATE
                  AND CAL-OPEN(WS-CAL-IDX) = "Y"
                   MOVE "Y" TO WS-DATE-OPEN
               END-IF
           END-PERFORM.

       COUNT-CYCLE-DAYS.
           MOVE 0 TO WS-CYCLE-DAYS
           PERFORM VARYING WS-CAL-IDX FROM 1 BY 1
               UNTIL WS-CAL-IDX > WS-CAL-COUNT
               IF CAL-DATE(WS-CAL-IDX) > WR-DATE(WS-IDX)
                  AND CAL-DATE(WS-CAL-IDX) <= WS-RETURN-DATE
                  AND CAL-OPEN(WS-CAL-IDX) = "Y"
                   ADD 1 TO WS-CYCLE-DAYS
               END-IF
           END-PERFORM.

''' + text[insert_at:]

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/wire_return_report.csv
test -s /app/out/wire_return_summary.txt
