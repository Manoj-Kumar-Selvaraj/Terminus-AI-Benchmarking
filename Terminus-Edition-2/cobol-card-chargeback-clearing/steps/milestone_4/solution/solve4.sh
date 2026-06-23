#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd /app
if ! grep -q 'CAL-FILE' /app/src/chargeback_clear.cbl; then
  bash "$STEPS_DIR/milestone_3/solution/solve3.sh"
fi
python3 <<'PY'
from pathlib import Path

path = Path("/app/src/chargeback_clear.cbl")
text = path.read_text()
if "MERCH-FILE" in text:
    path.write_text(text)
    raise SystemExit(0)

text = text.replace(
    '           SELECT CAL-FILE ASSIGN TO "/app/config/cycle_calendar.txt"\n'
    '               ORGANIZATION IS LINE SEQUENTIAL.',
    '           SELECT CAL-FILE ASSIGN TO "/app/config/cycle_calendar.txt"\n'
    '               ORGANIZATION IS LINE SEQUENTIAL.\n'
    '           SELECT MERCH-FILE ASSIGN TO "/app/config/merchants.csv"\n'
    '               ORGANIZATION IS LINE SEQUENTIAL.',
)
text = text.replace(
    "       FD CAL-FILE.\n       01 CAL-REC PIC X(32).",
    "       FD CAL-FILE.\n       01 CAL-REC PIC X(32).\n"
    "       FD MERCH-FILE.\n       01 MERCH-REC PIC X(64).",
)
text = text.replace(
    "       01 WS-EOF-CAL PIC X VALUE \"N\".",
    "       01 WS-EOF-CAL PIC X VALUE \"N\".\n"
    "       01 WS-EOF-MERCH PIC X VALUE \"N\".\n"
    "       01 WS-MERCH-COUNT PIC 9(4) COMP VALUE 0.\n"
    "       01 WS-MERCH-IDX PIC 9(4) COMP VALUE 0.\n"
    "       01 WS-MERCH-POS PIC 9(4) COMP VALUE 0.\n"
    "       01 WS-MERCH-OK PIC X VALUE \"N\".",
)
text = text.replace(
    "       01 WS-CALENDAR.",
    "       01 WS-MERCH-TABLE.\n"
    "          05 MERCH-ROW OCCURS 200 TIMES.\n"
    "             10 MERCH-ID PIC X(8).\n"
    "             10 MERCH-ENABLED PIC X.\n"
    "       01 WS-CALENDAR.",
)
text = text.replace(
    "           PERFORM LOAD-CALENDAR",
    "           PERFORM LOAD-CALENDAR\n           PERFORM LOAD-MERCHANTS",
)
load_merch = """
       LOAD-MERCHANTS.
           OPEN INPUT MERCH-FILE
           PERFORM UNTIL WS-EOF-MERCH = "Y"
               READ MERCH-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-MERCH
                   NOT AT END
                       IF MERCH-REC(1:11) NOT = "merchant_id"
                           ADD 1 TO WS-MERCH-COUNT
                           MOVE MERCH-REC(1:8) TO MERCH-ID(WS-MERCH-COUNT)
                           MOVE "N" TO MERCH-ENABLED(WS-MERCH-COUNT)
                           PERFORM VARYING WS-MERCH-POS FROM 10 BY 1
                               UNTIL WS-MERCH-POS > 55
                                  OR MERCH-ENABLED(WS-MERCH-COUNT) = "Y"
                               IF MERCH-REC(WS-MERCH-POS:4) = "true"
                                  OR MERCH-REC(WS-MERCH-POS:4) = "TRUE"
                                   MOVE "Y" TO MERCH-ENABLED(WS-MERCH-COUNT)
                               END-IF
                               IF MERCH-REC(WS-MERCH-POS:5) = "true "
                                  OR MERCH-REC(WS-MERCH-POS:5) = "TRUE "
                                  OR MERCH-REC(WS-MERCH-POS:5) = " true"
                                  OR MERCH-REC(WS-MERCH-POS:5) = " TRUE"
                                   MOVE "Y" TO MERCH-ENABLED(WS-MERCH-COUNT)
                               END-IF
                           END-PERFORM
                       END-IF
               END-READ
           END-PERFORM
           CLOSE MERCH-FILE.

       CHECK-MERCHANT-ENABLED.
           MOVE "N" TO WS-MERCH-OK
           PERFORM VARYING WS-MERCH-IDX FROM 1 BY 1
               UNTIL WS-MERCH-IDX > WS-MERCH-COUNT
                  OR WS-MERCH-OK = "Y"
               IF MERCH-ID(WS-MERCH-IDX) = SL-MERCHANT(WS-IDX)
                  AND MERCH-ENABLED(WS-MERCH-IDX) = "Y"
                   MOVE "Y" TO WS-MERCH-OK
               END-IF
           END-PERFORM.
"""
text = text.replace("       STORE-SALE.", load_merch + "\n       STORE-SALE.")
text = text.replace(
    "                   PERFORM CHECK-DATE-ELIGIBLE\n"
    "                   IF WS-DATE-ELIGIBLE = \"Y\"",
    "                   PERFORM CHECK-MERCHANT-ENABLED\n"
    "                   IF WS-MERCH-OK = \"Y\"\n"
    "                       PERFORM CHECK-DATE-ELIGIBLE\n"
    "                       IF WS-DATE-ELIGIBLE = \"Y\"",
)
text = text.replace(
    "                       END-IF\n"
    "                   END-IF\n"
    "               END-IF\n"
    "           END-PERFORM\n"
    "\n"
    "           IF WS-MATCH-IDX > 0",
    "                       END-IF\n"
    "                   END-IF\n"
    "                   END-IF\n"
    "               END-IF\n"
    "           END-PERFORM\n"
    "\n"
    "           IF WS-MATCH-IDX > 0",
    1,
)
path.write_text(text)
PY
/app/scripts/run_batch.sh
test -s /app/out/chargeback_report.csv
test -s /app/out/chargeback_summary.txt
