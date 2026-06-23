#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/lockbox_apply.cbl")
text = path.read_text()

if 'SELECT CALENDAR-FILE ASSIGN TO "/app/config/payment_calendar.txt"' not in text:
    text = text.replace(
        '    SELECT PAYMENT-FILE ASSIGN TO "/app/data/payments.dat"\n        ORGANIZATION IS LINE SEQUENTIAL.',
        '    SELECT PAYMENT-FILE ASSIGN TO "/app/data/payments.dat"\n        ORGANIZATION IS LINE SEQUENTIAL.\n    SELECT CALENDAR-FILE ASSIGN TO "/app/config/payment_calendar.txt"\n        ORGANIZATION IS LINE SEQUENTIAL.',
    )

if "FD CALENDAR-FILE." not in text:
    text = text.replace(
        "FD PAYMENT-FILE.\n01 PAYMENT-REC PIC X(80).",
        "FD PAYMENT-FILE.\n01 PAYMENT-REC PIC X(80).\n\nFD CALENDAR-FILE.\n01 CALENDAR-REC PIC X(16).",
    )

if '01 EOF-CALENDAR PIC X VALUE "N".' not in text:
    text = text.replace(
        '01 EOF-PAYMENT PIC X VALUE "N".',
        '01 EOF-PAYMENT PIC X VALUE "N".\n01 EOF-CALENDAR PIC X VALUE "N".',
    )

if "01 WS-CAL-COUNT PIC 9(4) COMP VALUE 0." not in text:
    text = text.replace(
        '01 WS-IDX PIC 9(4) COMP VALUE 0.',
        '01 WS-IDX PIC 9(4) COMP VALUE 0.\n01 WS-CAL-IDX PIC 9(4) COMP VALUE 0.\n01 WS-CAL-COUNT PIC 9(4) COMP VALUE 0.\n01 WS-TARGET-DATE PIC X(8).\n01 WS-DATE-OPEN PIC X VALUE "N".\n01 WS-PAY-DATE-OPEN PIC X VALUE "N".\n01 WS-CUTOFF-DATE-OPEN PIC X VALUE "N".',
    )

if "01 CALENDAR-TABLE." not in text:
    text = text.replace(
        "01 INVOICE-TABLE.",
        "01 CALENDAR-TABLE.\n   05 CALENDAR-ENTRY OCCURS 100 TIMES.\n      10 CAL-DATE PIC X(8).\n      10 CAL-OPEN PIC X.\n\n01 INVOICE-TABLE.",
    )

if "PERFORM LOAD-CALENDAR." not in text:
    text = text.replace(
        "MAIN.\n    PERFORM LOAD-INVOICES.",
        "MAIN.\n    PERFORM LOAD-CALENDAR.\n    PERFORM LOAD-INVOICES.",
    )

if "\nLOAD-CALENDAR.\n" not in text:
    text = text.replace(
        "\nLOAD-INVOICES.\n",
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

LOAD-INVOICES.
''',
    )

start = text.index("FIND-MATCH.")
end = text.index("WRITE-REPORT-ROW.")
text = text[:start] + '''FIND-MATCH.
    MOVE 0 TO WS-MATCH-IDX.
    PERFORM VARYING WS-IDX FROM 1 BY 1
        UNTIL WS-IDX > WS-INVOICE-COUNT
        MOVE WS-PAY-DATE TO WS-TARGET-DATE
        PERFORM CHECK-DATE-OPEN
        MOVE WS-DATE-OPEN TO WS-PAY-DATE-OPEN
        MOVE INV-CUTOFF-DATE(WS-IDX) TO WS-TARGET-DATE
        PERFORM CHECK-DATE-OPEN
        MOVE WS-DATE-OPEN TO WS-CUTOFF-DATE-OPEN
        IF INV-USED(WS-IDX) NOT = "Y"
            AND WS-PAY-DATE-OPEN = "Y"
            AND WS-CUTOFF-DATE-OPEN = "Y"
            AND INV-ID(WS-IDX) = WS-PAY-INVOICE
            AND INV-CUSTOMER(WS-IDX) = WS-PAY-CUSTOMER
            AND INV-AMOUNT(WS-IDX) = WS-PAY-AMOUNT
            AND INV-STATUS(WS-IDX) = "O"
            AND INV-HOLD(WS-IDX) = "N"
            AND WS-PAY-DISPOSITION = "P"
            AND WS-PAY-DATE <= INV-CUTOFF-DATE(WS-IDX)
            AND (INV-CHANNEL(WS-IDX) = "ACH"
                 OR INV-CHANNEL(WS-IDX) = "WIR"
                 OR INV-CHANNEL(WS-IDX) = "CRD"
                 OR INV-CHANNEL(WS-IDX) = "LBX")
            AND INV-CHANNEL(WS-IDX) = WS-PAY-CHANNEL
                IF WS-MATCH-IDX = 0
                    MOVE WS-IDX TO WS-MATCH-IDX
                ELSE
                    IF INV-CUTOFF-DATE(WS-IDX) > INV-CUTOFF-DATE(WS-MATCH-IDX)
                        MOVE WS-IDX TO WS-MATCH-IDX
                    END-IF
                END-IF
        END-IF
    END-PERFORM.

CHECK-DATE-OPEN.
    MOVE "N" TO WS-DATE-OPEN.
    PERFORM VARYING WS-CAL-IDX FROM 1 BY 1
        UNTIL WS-CAL-IDX > WS-CAL-COUNT
        IF CAL-DATE(WS-CAL-IDX) = WS-TARGET-DATE
            AND CAL-OPEN(WS-CAL-IDX) = "Y"
                MOVE "Y" TO WS-DATE-OPEN
        END-IF
    END-PERFORM.

''' + text[end:]

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/lockbox_report.csv
test -s /app/out/lockbox_summary.txt
