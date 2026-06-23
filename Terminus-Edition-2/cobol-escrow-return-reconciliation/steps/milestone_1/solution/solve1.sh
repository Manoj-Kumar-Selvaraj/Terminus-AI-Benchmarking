#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path

path = Path("/app/src/wire_returns.cbl")
text = path.read_text()

text = text.replace(
    'IF WR-ID(WS-IDX)(1:10) = WS-RETURN-WIRE(1:10)',
    'IF WR-ID(WS-IDX) = WS-RETURN-WIRE',
)
text = text.replace(
    'SUBTRACT WS-RETURN-AMOUNT FROM WS-CLEARED-AMOUNT',
    'ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT',
)

if 'SELECT REASON-FILE' not in text:
    text = text.replace(
        '           SELECT SUMMARY-FILE ASSIGN TO "/app/out/wire_return_summary.txt"\n'
        '               ORGANIZATION IS LINE SEQUENTIAL.',
        '           SELECT SUMMARY-FILE ASSIGN TO "/app/out/wire_return_summary.txt"\n'
        '               ORGANIZATION IS LINE SEQUENTIAL.\n'
        '           SELECT REASON-FILE ASSIGN TO "/app/config/reason_codes.csv"\n'
        '               ORGANIZATION IS LINE SEQUENTIAL.',
    )

if 'FD REASON-FILE.' not in text:
    text = text.replace(
        '       FD SUMMARY-FILE.\n       01 SUMMARY-REC PIC X(80).',
        '       FD SUMMARY-FILE.\n       01 SUMMARY-REC PIC X(80).\n'
        '       FD REASON-FILE.\n       01 REASON-REC PIC X(80).',
    )

if 'WS-REASON-COUNT' not in text:
    text = text.replace(
        '       01 WS-RETURN-ACCOUNT PIC X(8).',
        '       01 WS-RETURN-ACCOUNT PIC X(8).\n'
        '       01 WS-EOF-REASON PIC X VALUE "N".\n'
        '       01 WS-REASON-COUNT PIC 9(4) COMP VALUE 0.\n'
        '       01 WS-REASON-IDX PIC 9(4) COMP VALUE 0.\n'
        '       01 WS-CHECK-REASON PIC X(8).\n'
        '       01 WS-REASON-OK PIC X VALUE "N".\n'
        '       01 WS-REASON-CODE PIC X(8).\n'
        '       01 WS-REASON-REST PIC X(72).\n'
        '       01 REASON-TABLE.\n'
        '          05 ALLOWED-REASON OCCURS 50 TIMES PIC X(8).',
    )

if 'PERFORM LOAD-REASON-CODES' not in text:
    text = text.replace(
        '       MAIN-PARA.\n           OPEN INPUT WIRE-FILE',
        '       MAIN-PARA.\n           PERFORM LOAD-REASON-CODES\n           OPEN INPUT WIRE-FILE',
    )

if 'LOAD-REASON-CODES.' not in text:
    text = text.replace(
        '       STORE-WIRE.',
        '''       LOAD-REASON-CODES.
           MOVE 0 TO WS-REASON-COUNT
           OPEN INPUT REASON-FILE
           PERFORM UNTIL WS-EOF-REASON = "Y"
               READ REASON-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-REASON
                   NOT AT END
                       IF REASON-REC(1:4) NOT = "code"
                           UNSTRING REASON-REC DELIMITED BY ","
                               INTO WS-REASON-CODE WS-REASON-REST
                           END-UNSTRING
                           IF FUNCTION TRIM(WS-REASON-CODE) NOT = SPACES
                               ADD 1 TO WS-REASON-COUNT
                               MOVE FUNCTION TRIM(WS-REASON-CODE)
                                   TO ALLOWED-REASON(WS-REASON-COUNT)
                           END-IF
                       END-IF
               END-READ
           END-PERFORM
           CLOSE REASON-FILE.

       CHECK-REASON-ALLOWED.
           MOVE "N" TO WS-REASON-OK
           PERFORM VARYING WS-REASON-IDX FROM 1 BY 1
               UNTIL WS-REASON-IDX > WS-REASON-COUNT
               IF FUNCTION TRIM(ALLOWED-REASON(WS-REASON-IDX))
                  = FUNCTION TRIM(WS-CHECK-REASON)
                   MOVE "Y" TO WS-REASON-OK
               END-IF
           END-PERFORM.

       STORE-WIRE.''',
    )

old_reason_block = '''               IF WR-ID(WS-IDX) = WS-RETURN-WIRE
                  AND WR-ACCOUNT(WS-IDX) = WS-RETURN-ACCOUNT
                  AND WR-AMOUNT(WS-IDX) = WS-RETURN-AMOUNT
                  AND WR-STATUS(WS-IDX) = "S"
                  AND (WR-REASON(WS-IDX) = "CON"
                       OR WR-REASON(WS-IDX) = "REF"
                       OR WR-REASON(WS-IDX) = "ADM")
                   MOVE WS-IDX TO WS-MATCH-IDX
               END-IF'''

new_reason_block = '''               IF WR-ID(WS-IDX) = WS-RETURN-WIRE
                  AND WR-ACCOUNT(WS-IDX) = WS-RETURN-ACCOUNT
                  AND WR-AMOUNT(WS-IDX) = WS-RETURN-AMOUNT
                  AND WR-STATUS(WS-IDX) = "S"
                   MOVE WR-REASON(WS-IDX) TO WS-CHECK-REASON
                   PERFORM CHECK-REASON-ALLOWED
                   IF WS-REASON-OK = "Y"
                       MOVE WS-IDX TO WS-MATCH-IDX
                   END-IF
               END-IF'''

if old_reason_block in text:
    text = text.replace(old_reason_block, new_reason_block)

path.write_text(text)
PY
/app/scripts/run_batch.sh
test -s /app/out/wire_return_report.csv
test -s /app/out/wire_return_summary.txt
