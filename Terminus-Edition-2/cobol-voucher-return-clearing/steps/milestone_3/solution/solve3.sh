#!/usr/bin/env bash
set -euo pipefail
cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/voucher_returns.cbl")
text = path.read_text()

# Re-apply milestone 1 fixes when this oracle is run from a fresh container.
text = text.replace('IF WR-ID(WS-IDX)(1:10) = WS-RETURN-VOUCHER(1:10)', 'IF WR-ID(WS-IDX) = WS-RETURN-VOUCHER')
if 'OR WR-REASON(WS-IDX) = "B2B")' not in text:
    text = text.replace('OR WR-REASON(WS-IDX) = "ADM")', 'OR WR-REASON(WS-IDX) = "ADM"\n                       OR WR-REASON(WS-IDX) = "B2B")')
text = text.replace('SUBTRACT WS-RETURN-AMOUNT FROM WS-CLEARED-AMOUNT', 'ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT')

# Re-apply milestone 2 consumption fixes when needed.
if '10 WR-USED PIC X.' not in text:
    text = text.replace('             10 WR-STATUS PIC X.', '             10 WR-STATUS PIC X.\n             10 WR-USED PIC X.')
if 'MOVE "N" TO WR-USED(WS-VOUCHER-COUNT)' not in text:
    text = text.replace('           MOVE VOUCHER-REC(35:1) TO WR-STATUS(WS-VOUCHER-COUNT).', '           MOVE VOUCHER-REC(35:1) TO WR-STATUS(WS-VOUCHER-COUNT)\n           MOVE "N" TO WR-USED(WS-VOUCHER-COUNT).')
if 'IF WR-USED(WS-IDX) NOT = "Y"' not in text:
    text = text.replace('IF WR-ID(WS-IDX) = WS-RETURN-VOUCHER\n                  AND WR-ACCOUNT', 'IF WR-USED(WS-IDX) NOT = "Y"\n                  AND WR-ID(WS-IDX) = WS-RETURN-VOUCHER\n                  AND WR-ACCOUNT')
if 'MOVE "Y" TO WR-USED(WS-MATCH-IDX)' not in text:
    text = text.replace('ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT', 'ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT\n               MOVE "Y" TO WR-USED(WS-MATCH-IDX)')

text = text.replace(
    '           SELECT RETURN-FILE ASSIGN TO "/app/data/returns.dat"\n               ORGANIZATION IS LINE SEQUENTIAL.',
    '           SELECT RETURN-FILE ASSIGN TO "/app/data/returns.dat"\n               ORGANIZATION IS LINE SEQUENTIAL.\n           SELECT CALENDAR-FILE ASSIGN TO "/app/config/cycle_calendar.txt"\n               ORGANIZATION IS LINE SEQUENTIAL.',
)
text = text.replace(
    '       FD RETURN-FILE.\n       01 RETURN-REC PIC X(64).',
    '       FD RETURN-FILE.\n       01 RETURN-REC PIC X(64).\n       FD CALENDAR-FILE.\n       01 CALENDAR-REC PIC X(16).',
)
text = text.replace(
    '       01 WS-EOF-RETURN PIC X VALUE "N".',
    '       01 WS-EOF-RETURN PIC X VALUE "N".\n       01 WS-EOF-CALENDAR PIC X VALUE "N".',
)
text = text.replace(
    '       01 WS-IDX PIC 9(4) COMP VALUE 0.',
    '       01 WS-IDX PIC 9(4) COMP VALUE 0.\n       01 WS-CAL-IDX PIC 9(4) COMP VALUE 0.\n       01 WS-CAL-COUNT PIC 9(4) COMP VALUE 0.\n       01 WS-CYCLE-DAYS PIC 9(4) VALUE 0.\n       01 WS-TARGET-DATE PIC X(8).\n       01 WS-DATE-OPEN PIC X VALUE "N".\n       01 WS-VOUCHER-DATE-OPEN PIC X VALUE "N".\n       01 WS-RETURN-DATE-OPEN PIC X VALUE "N".',
)
text = text.replace(
    '       01 WS-RETURN-ACCOUNT PIC X(8).',
    '       01 WS-RETURN-ACCOUNT PIC X(8).\n       01 WS-RETURN-DATE PIC X(8).',
)
text = text.replace(
    '             10 WR-STATUS PIC X.',
    '             10 WR-STATUS PIC X.\n             10 WR-DATE PIC X(8).',
)
text = text.replace(
    '       PROCEDURE DIVISION.',
    '       01 CALENDAR-TABLE.\n          05 CAL-ENTRY OCCURS 100 TIMES.\n             10 CAL-DATE PIC X(8).\n             10 CAL-OPEN PIC X.\n\n       PROCEDURE DIVISION.',
)
text = text.replace(
    '       MAIN-PARA.\n           OPEN INPUT VOUCHER-FILE',
    '       MAIN-PARA.\n           PERFORM LOAD-CALENDAR\n           OPEN INPUT VOUCHER-FILE',
)
text = text.replace(
    '       STORE-VOUCHER.',
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

       STORE-VOUCHER.''',
)
text = text.replace(
    '           MOVE VOUCHER-REC(35:1) TO WR-STATUS(WS-VOUCHER-COUNT)\n           MOVE "N" TO WR-USED(WS-VOUCHER-COUNT).',
    '           MOVE VOUCHER-REC(35:1) TO WR-STATUS(WS-VOUCHER-COUNT)\n           MOVE "N" TO WR-USED(WS-VOUCHER-COUNT)\n           MOVE VOUCHER-REC(36:8) TO WR-DATE(WS-VOUCHER-COUNT).',
)
text = text.replace(
    '           MOVE RETURN-REC(24:8) TO WS-RETURN-ACCOUNT',
    '           MOVE RETURN-REC(24:8) TO WS-RETURN-ACCOUNT\n           MOVE RETURN-REC(32:8) TO WS-RETURN-DATE',
)

start = text.index('           PERFORM VARYING WS-IDX FROM 1 BY 1')
end = text.index('\n\n           IF WS-MATCH-IDX > 0', start)
text = text[:start] + '''           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > WS-VOUCHER-COUNT
               MOVE WR-DATE(WS-IDX) TO WS-TARGET-DATE
               PERFORM CHECK-DATE-OPEN
               MOVE WS-DATE-OPEN TO WS-VOUCHER-DATE-OPEN
               MOVE WS-RETURN-DATE TO WS-TARGET-DATE
               PERFORM CHECK-DATE-OPEN
               MOVE WS-DATE-OPEN TO WS-RETURN-DATE-OPEN
               PERFORM COUNT-CYCLE-DAYS
               IF WR-USED(WS-IDX) NOT = "Y"
                  AND WS-VOUCHER-DATE-OPEN = "Y"
                  AND WS-RETURN-DATE-OPEN = "Y"
                  AND WS-RETURN-DATE >= WR-DATE(WS-IDX)
                  AND WS-CYCLE-DAYS <= 2
                  AND WR-ID(WS-IDX) = WS-RETURN-VOUCHER
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
test -s /app/out/voucher_return_report.csv
test -s /app/out/voucher_return_summary.txt
