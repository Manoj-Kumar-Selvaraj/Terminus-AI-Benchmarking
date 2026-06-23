#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/ach_reconcile.cbl")
text = path.read_text()

if 'SELECT CALENDAR-FILE ASSIGN TO "/app/config/business_calendar.txt"' not in text:
    text = text.replace(
        '    SELECT REVERSAL-FILE ASSIGN TO "/app/data/reversals.dat"\n        ORGANIZATION IS LINE SEQUENTIAL.',
        '    SELECT REVERSAL-FILE ASSIGN TO "/app/data/reversals.dat"\n        ORGANIZATION IS LINE SEQUENTIAL.\n    SELECT CALENDAR-FILE ASSIGN TO "/app/config/business_calendar.txt"\n        ORGANIZATION IS LINE SEQUENTIAL.',
    )
if 'FD CALENDAR-FILE.' not in text:
    text = text.replace(
        'FD REVERSAL-FILE.\n01 REVERSAL-REC PIC X(45).',
        'FD REVERSAL-FILE.\n01 REVERSAL-REC PIC X(45).\n\nFD CALENDAR-FILE.\n01 CALENDAR-REC PIC X(16).',
    )
if '01 EOF-CALENDAR PIC X VALUE "N".' not in text:
    text = text.replace(
        '01 EOF-REVERSAL PIC X VALUE "N".',
        '01 EOF-REVERSAL PIC X VALUE "N".\n01 EOF-CALENDAR PIC X VALUE "N".',
    )
if '01 WS-CAL-COUNT PIC 9(4) COMP VALUE 0.' not in text:
    text = text.replace(
        '01 WS-SETTLE-COUNT PIC 9(4) COMP VALUE 0.',
        '01 WS-SETTLE-COUNT PIC 9(4) COMP VALUE 0.\n01 WS-CAL-COUNT PIC 9(4) COMP VALUE 0.\n01 WS-CAL-IDX PIC 9(4) COMP VALUE 0.\n01 WS-BANK-DAYS PIC 9(3) VALUE 0.',
    )
if '01 CALENDAR-TABLE.' not in text:
    text = text.replace(
        '01 WS-STATUS PIC X(9).',
        '01 WS-STATUS PIC X(9).\n\n01 CALENDAR-TABLE.\n   05 CALENDAR-ENTRY OCCURS 100 TIMES.\n      10 CAL-DATE PIC X(8).\n      10 CAL-OPEN PIC X.',
    )
if 'PERFORM LOAD-CALENDAR.' not in text:
    text = text.replace(
        'MAIN.\n    PERFORM LOAD-SETTLEMENTS.',
        'MAIN.\n    PERFORM LOAD-CALENDAR.\n    PERFORM LOAD-SETTLEMENTS.',
    )
if '\nLOAD-CALENDAR.\n' not in text:
    text = text.replace(
        '\nLOAD-SETTLEMENTS.\n    OPEN INPUT SETTLE-FILE.',
        '''\nLOAD-CALENDAR.
    OPEN INPUT CALENDAR-FILE.
    PERFORM UNTIL EOF-CALENDAR = "Y"
        READ CALENDAR-FILE
            AT END
                MOVE "Y" TO EOF-CALENDAR
            NOT AT END
                IF CALENDAR-REC(1:8) NOT = SPACES
                    ADD 1 TO WS-CAL-COUNT
                    MOVE CALENDAR-REC(1:8) TO CAL-DATE(WS-CAL-COUNT)
                    IF CALENDAR-REC(10:4) = "OPEN"
                        MOVE "Y" TO CAL-OPEN(WS-CAL-COUNT)
                    ELSE
                        MOVE "N" TO CAL-OPEN(WS-CAL-COUNT)
                    END-IF
                END-IF
        END-READ
    END-PERFORM.
    CLOSE CALENDAR-FILE.

LOAD-SETTLEMENTS.
    OPEN INPUT SETTLE-FILE.''',
    )

start = text.index('FIND-MATCH.')
end = text.index('WRITE-REPORT-ROW.')
text = text[:start] + '''FIND-MATCH.
    MOVE 0 TO WS-MATCH-IDX.
    PERFORM VARYING WS-IDX FROM 1 BY 1
        UNTIL WS-IDX > WS-SETTLE-COUNT
        PERFORM COUNT-BUSINESS-DAYS
        IF SET-USED(WS-IDX) NOT = "Y"
            AND SET-TRACE(WS-IDX) = WS-REV-TRACE
            AND SET-COMPANY(WS-IDX) = WS-REV-COMPANY
            AND SET-AMOUNT(WS-IDX) = WS-REV-AMOUNT
            AND SET-DIRECTION(WS-IDX) = "C"
            AND SET-STATUS(WS-IDX) = "P"
            AND WS-REV-DATE >= SET-DATE(WS-IDX)
            AND ((WS-REV-REASON = "R01" AND WS-BANK-DAYS <= 1)
                 OR (WS-REV-REASON = "R02" AND WS-BANK-DAYS <= 1)
                 OR (WS-REV-REASON = "R03" AND WS-BANK-DAYS <= 2)
                 OR (WS-REV-REASON = "R10" AND WS-BANK-DAYS <= 2))
            AND (SET-SEC(WS-IDX) = "PPD"
                 OR SET-SEC(WS-IDX) = "CCD"
                 OR SET-SEC(WS-IDX) = "WEB"
                 OR SET-SEC(WS-IDX) = "TEL")
                IF WS-MATCH-IDX = 0
                    MOVE WS-IDX TO WS-MATCH-IDX
                ELSE
                    IF SET-DATE(WS-IDX) > SET-DATE(WS-MATCH-IDX)
                        MOVE WS-IDX TO WS-MATCH-IDX
                    END-IF
                END-IF
        END-IF
    END-PERFORM.

COUNT-BUSINESS-DAYS.
    MOVE 0 TO WS-BANK-DAYS.
    PERFORM VARYING WS-CAL-IDX FROM 1 BY 1
        UNTIL WS-CAL-IDX > WS-CAL-COUNT
        IF CAL-DATE(WS-CAL-IDX) > SET-DATE(WS-IDX)
            AND CAL-DATE(WS-CAL-IDX) <= WS-REV-DATE
            AND CAL-OPEN(WS-CAL-IDX) = "Y"
                ADD 1 TO WS-BANK-DAYS
        END-IF
    END-PERFORM.

''' + text[end:]
path.write_text(text)
PY

/app/scripts/run_batch.sh
