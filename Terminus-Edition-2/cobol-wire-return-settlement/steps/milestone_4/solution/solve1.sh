#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path

path = Path("/app/src/wire_returns.cbl")
text = path.read_text()

if 'SELECT REASON-FILE ASSIGN TO "/app/config/reason_codes.csv"' in text:
    raise SystemExit(0)

text = text.replace(
    '           SELECT RETURN-FILE ASSIGN TO "/app/data/returns.dat"\n               ORGANIZATION IS LINE SEQUENTIAL.',
    '           SELECT RETURN-FILE ASSIGN TO "/app/data/returns.dat"\n               ORGANIZATION IS LINE SEQUENTIAL.\n           SELECT REASON-FILE ASSIGN TO "/app/config/reason_codes.csv"\n               ORGANIZATION IS LINE SEQUENTIAL.',
)
text = text.replace(
    '       FD RETURN-FILE.\n       01 RETURN-REC PIC X(64).',
    '       FD RETURN-FILE.\n       01 RETURN-REC PIC X(64).\n       FD REASON-FILE.\n       01 REASON-REC PIC X(80).',
)
text = text.replace(
    '       01 WS-EOF-RETURN PIC X VALUE "N".',
    '       01 WS-EOF-RETURN PIC X VALUE "N".\n       01 WS-EOF-REASON PIC X VALUE "N".',
)
text = text.replace(
    '       01 WS-MATCH-IDX PIC 9(4) COMP VALUE 0.',
    '       01 WS-MATCH-IDX PIC 9(4) COMP VALUE 0.\n       01 WS-REASON-COUNT PIC 9(4) COMP VALUE 0.\n       01 WS-REASON-IDX PIC 9(4) COMP VALUE 0.\n       01 WS-REASON-ALLOWED PIC X VALUE "N".\n       01 WS-REASON-CODE PIC X(3).\n       01 WS-REASON-FIELD PIC X(24).',
)
text = text.replace(
    '       01 WS-WIRES.',
    '       01 REASON-TABLE.\n          05 RC-ENTRY OCCURS 100 TIMES.\n             10 RC-CODE PIC X(3).\n       01 WS-WIRES.',
)
text = text.replace(
    '       MAIN-PARA.\n           OPEN INPUT WIRE-FILE',
    '       MAIN-PARA.\n           PERFORM LOAD-REASON-CODES\n           OPEN INPUT WIRE-FILE',
)
text = text.replace(
    'IF WR-ID(WS-IDX)(1:10) = WS-RETURN-WIRE(1:10)',
    'IF WR-ID(WS-IDX) = WS-RETURN-WIRE',
)
text = text.replace(
    '''               IF WR-ID(WS-IDX) = WS-RETURN-WIRE
                  AND WR-ACCOUNT(WS-IDX) = WS-RETURN-ACCOUNT
                  AND WR-AMOUNT(WS-IDX) = WS-RETURN-AMOUNT
                  AND WR-STATUS(WS-IDX) = "S"
                  AND (WR-REASON(WS-IDX) = "CON"
                       OR WR-REASON(WS-IDX) = "REF"
                       OR WR-REASON(WS-IDX) = "ADM")
                   MOVE WS-IDX TO WS-MATCH-IDX
               END-IF''',
    '''               IF WR-ID(WS-IDX) = WS-RETURN-WIRE
                  AND WR-ACCOUNT(WS-IDX) = WS-RETURN-ACCOUNT
                  AND WR-AMOUNT(WS-IDX) = WS-RETURN-AMOUNT
                  AND WR-STATUS(WS-IDX) = "S"
                   PERFORM CHECK-REASON-ALLOWED
                   IF WS-REASON-ALLOWED = "Y"
                       MOVE WS-IDX TO WS-MATCH-IDX
                   END-IF
               END-IF''',
)
text = text.replace(
    'SUBTRACT WS-RETURN-AMOUNT FROM WS-CLEARED-AMOUNT',
    'ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT',
)

insert_at = text.index('       STORE-WIRE.')
reason_paragraphs = '''       LOAD-REASON-CODES.
           MOVE 0 TO WS-REASON-COUNT
           OPEN INPUT REASON-FILE
           PERFORM UNTIL WS-EOF-REASON = "Y"
               READ REASON-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-REASON
                   NOT AT END
                       MOVE SPACES TO WS-REASON-FIELD
                       UNSTRING REASON-REC DELIMITED BY ","
                           INTO WS-REASON-FIELD
                       END-UNSTRING
                       MOVE FUNCTION TRIM(WS-REASON-FIELD) TO WS-REASON-CODE
                       IF WS-REASON-CODE NOT = "code"
                          AND WS-REASON-CODE NOT = SPACES
                           ADD 1 TO WS-REASON-COUNT
                           MOVE WS-REASON-CODE TO RC-CODE(WS-REASON-COUNT)
                       END-IF
               END-READ
           END-PERFORM
           CLOSE REASON-FILE.

       CHECK-REASON-ALLOWED.
           MOVE "N" TO WS-REASON-ALLOWED
           PERFORM VARYING WS-REASON-IDX FROM 1 BY 1
               UNTIL WS-REASON-IDX > WS-REASON-COUNT
               IF RC-CODE(WS-REASON-IDX) = WR-REASON(WS-IDX)
                   MOVE "Y" TO WS-REASON-ALLOWED
               END-IF
           END-PERFORM.

'''
text = text[:insert_at] + reason_paragraphs + text[insert_at:]
path.write_text(text)
PY
/app/scripts/run_batch.sh
test -s /app/out/wire_return_report.csv
test -s /app/out/wire_return_summary.txt
