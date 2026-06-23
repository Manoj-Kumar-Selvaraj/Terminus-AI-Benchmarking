#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path

path = Path("/app/src/chargeback_clear.cbl")
text = path.read_text()

if "SL-USED" not in text:
    text = text.replace(
        "             10 SL-STATUS PIC X.",
        "             10 SL-STATUS PIC X.\n             10 SL-USED PIC X.",
    )
    text = text.replace(
        "           MOVE SALE-REC(35:1) TO SL-STATUS(WS-SALE-COUNT).",
        "           MOVE SALE-REC(35:1) TO SL-STATUS(WS-SALE-COUNT)\n"
        "           MOVE \"N\" TO SL-USED(WS-SALE-COUNT).",
    )

old_process = """       PROCESS-CHARGEBACK.
           MOVE CHGBK-REC(2:12) TO WS-CHGBK-SALE
           MOVE CHGBK-REC(14:10) TO WS-CHGBK-AMOUNT
           MOVE CHGBK-REC(24:8) TO WS-CHGBK-MERCHANT
           MOVE 0 TO WS-MATCH-IDX
           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > WS-SALE-COUNT OR WS-MATCH-IDX > 0
               IF SL-ID(WS-IDX) = WS-CHGBK-SALE
                  AND SL-MERCHANT(WS-IDX) = WS-CHGBK-MERCHANT
                  AND SL-AMOUNT(WS-IDX) = WS-CHGBK-AMOUNT
                  AND SL-STATUS(WS-IDX) = "S"
                  AND (SL-REASON(WS-IDX) = "F10"
                       OR SL-REASON(WS-IDX) = "F20"
                       OR SL-REASON(WS-IDX) = "R99"
                       OR SL-REASON(WS-IDX) = "MRC")
                   MOVE WS-IDX TO WS-MATCH-IDX
               END-IF
           END-PERFORM

           IF WS-MATCH-IDX > 0
               ADD 1 TO WS-APPLIED-COUNT
               ADD WS-CHGBK-AMOUNT TO WS-APPLIED-AMOUNT
           ELSE
               ADD 1 TO WS-EXCEPTION-COUNT
               ADD WS-CHGBK-AMOUNT TO WS-EXCEPTION-AMOUNT
           END-IF
           PERFORM WRITE-REPORT-ROW."""

new_process = """       PROCESS-CHARGEBACK.
           MOVE CHGBK-REC(2:12) TO WS-CHGBK-SALE
           MOVE CHGBK-REC(14:10) TO WS-CHGBK-AMOUNT
           MOVE CHGBK-REC(24:8) TO WS-CHGBK-MERCHANT
           MOVE 0 TO WS-MATCH-IDX
           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > WS-SALE-COUNT
               IF WS-MATCH-IDX = 0
                  AND SL-USED(WS-IDX) NOT = "Y"
                  AND SL-ID(WS-IDX) = WS-CHGBK-SALE
                  AND SL-MERCHANT(WS-IDX) = WS-CHGBK-MERCHANT
                  AND SL-AMOUNT(WS-IDX) = WS-CHGBK-AMOUNT
                  AND SL-STATUS(WS-IDX) = "S"
                  AND (SL-REASON(WS-IDX) = "F10"
                       OR SL-REASON(WS-IDX) = "F20"
                       OR SL-REASON(WS-IDX) = "R99"
                       OR SL-REASON(WS-IDX) = "MRC")
                   MOVE WS-IDX TO WS-MATCH-IDX
               END-IF
           END-PERFORM

           IF WS-MATCH-IDX > 0
               ADD 1 TO WS-APPLIED-COUNT
               ADD WS-CHGBK-AMOUNT TO WS-APPLIED-AMOUNT
               MOVE "Y" TO SL-USED(WS-MATCH-IDX)
           ELSE
               ADD 1 TO WS-EXCEPTION-COUNT
               ADD WS-CHGBK-AMOUNT TO WS-EXCEPTION-AMOUNT
           END-IF
           PERFORM WRITE-REPORT-ROW."""

if old_process not in text:
    raise SystemExit("milestone 2 COBOL patch anchor missing")
path.write_text(text.replace(old_process, new_process))
PY
/app/scripts/run_batch.sh
test -s /app/out/chargeback_report.csv
test -s /app/out/chargeback_summary.txt
