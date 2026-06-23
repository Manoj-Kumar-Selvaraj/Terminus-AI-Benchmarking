#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path

Path("/app/src/chargeback_clear.cbl").write_text(r'''       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARD-CLEAR.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SALE-FILE ASSIGN TO "/app/data/sales.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CHGBK-FILE ASSIGN TO "/app/data/chargebacks.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CAL-FILE ASSIGN TO "/app/config/cycle_calendar.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT REPORT-FILE ASSIGN TO "/app/out/chargeback_report.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUMMARY-FILE ASSIGN TO "/app/out/chargeback_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD SALE-FILE.
       01 SALE-REC PIC X(80).
       FD CHGBK-FILE.
       01 CHGBK-REC PIC X(80).
       FD CAL-FILE.
       01 CAL-REC PIC X(32).
       FD REPORT-FILE.
       01 REPORT-REC PIC X(160).
       FD SUMMARY-FILE.
       01 SUMMARY-REC PIC X(80).

       WORKING-STORAGE SECTION.
       01 WS-EOF-SALE PIC X VALUE "N".
       01 WS-EOF-CHGBK PIC X VALUE "N".
       01 WS-EOF-CAL PIC X VALUE "N".
       01 WS-IDX PIC 9(4) COMP VALUE 0.
       01 WS-CAL-IDX PIC 9(4) COMP VALUE 0.
       01 WS-SALE-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-CAL-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-MATCH-IDX PIC 9(4) COMP VALUE 0.
       01 WS-APPLIED-COUNT PIC 9(6) VALUE 0.
       01 WS-EXCEPTION-COUNT PIC 9(6) VALUE 0.
       01 WS-APPLIED-AMOUNT PIC 9(12) VALUE 0.
       01 WS-EXCEPTION-AMOUNT PIC 9(12) VALUE 0.
       01 WS-CHGBK-SALE PIC X(12).
       01 WS-CHGBK-AMOUNT PIC 9(10).
       01 WS-CHGBK-MERCHANT PIC X(8).
       01 WS-CHGBK-DATE PIC X(8).
       01 WS-CHECK-DATE PIC X(8).
       01 WS-DATE-OPEN PIC X VALUE "N".
       01 WS-DATE-ELIGIBLE PIC X VALUE "N".
       01 WS-OPEN-DAYS PIC 9(4) VALUE 0.
       01 WS-SALES.
          05 SALE-TABLE OCCURS 250 TIMES.
             10 SL-ID PIC X(12).
             10 SL-REASON PIC X(3).
             10 SL-AMOUNT PIC 9(10).
             10 SL-MERCHANT PIC X(8).
             10 SL-STATUS PIC X.
             10 SL-DATE PIC X(8).
             10 SL-USED PIC X.
       01 WS-CALENDAR.
          05 CAL-TABLE OCCURS 400 TIMES.
             10 CAL-DATE PIC X(8).
             10 CAL-OPEN PIC X.

       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM LOAD-CALENDAR
           OPEN INPUT SALE-FILE
           PERFORM UNTIL WS-EOF-SALE = "Y"
               READ SALE-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-SALE
                   NOT AT END
                       PERFORM STORE-SALE
               END-READ
           END-PERFORM
           CLOSE SALE-FILE

           OPEN INPUT CHGBK-FILE
           OPEN OUTPUT REPORT-FILE
           OPEN OUTPUT SUMMARY-FILE
           MOVE SPACES TO REPORT-REC
           MOVE "sale_id,merchant_id,reason,amount_cents,status" TO REPORT-REC
           WRITE REPORT-REC

           PERFORM UNTIL WS-EOF-CHGBK = "Y"
               READ CHGBK-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-CHGBK
                   NOT AT END
                       PERFORM PROCESS-CHARGEBACK
               END-READ
           END-PERFORM

           PERFORM WRITE-SUMMARY
           CLOSE CHGBK-FILE
           CLOSE REPORT-FILE
           CLOSE SUMMARY-FILE
           STOP RUN.

       LOAD-CALENDAR.
           OPEN INPUT CAL-FILE
           PERFORM UNTIL WS-EOF-CAL = "Y"
               READ CAL-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-CAL
                   NOT AT END
                       ADD 1 TO WS-CAL-COUNT
                       MOVE CAL-REC(1:8) TO CAL-DATE(WS-CAL-COUNT)
                       IF CAL-REC(10:4) = "OPEN"
                           MOVE "Y" TO CAL-OPEN(WS-CAL-COUNT)
                       ELSE
                           MOVE "N" TO CAL-OPEN(WS-CAL-COUNT)
                       END-IF
               END-READ
           END-PERFORM
           CLOSE CAL-FILE.

       STORE-SALE.
           ADD 1 TO WS-SALE-COUNT
           MOVE SALE-REC(2:12) TO SL-ID(WS-SALE-COUNT)
           MOVE SALE-REC(14:3) TO SL-REASON(WS-SALE-COUNT)
           IF SL-REASON(WS-SALE-COUNT) = "FRD"
               MOVE "F10" TO SL-REASON(WS-SALE-COUNT)
           END-IF
           IF SL-REASON(WS-SALE-COUNT) = "M20"
               MOVE "F20" TO SL-REASON(WS-SALE-COUNT)
           END-IF
           IF SL-REASON(WS-SALE-COUNT) = "MER"
               MOVE "MRC" TO SL-REASON(WS-SALE-COUNT)
           END-IF
           MOVE SALE-REC(17:10) TO SL-AMOUNT(WS-SALE-COUNT)
           MOVE SALE-REC(27:8) TO SL-MERCHANT(WS-SALE-COUNT)
           MOVE SALE-REC(35:1) TO SL-STATUS(WS-SALE-COUNT)
           MOVE SALE-REC(36:8) TO SL-DATE(WS-SALE-COUNT)
           MOVE "N" TO SL-USED(WS-SALE-COUNT).

       PROCESS-CHARGEBACK.
           MOVE CHGBK-REC(2:12) TO WS-CHGBK-SALE
           MOVE CHGBK-REC(14:10) TO WS-CHGBK-AMOUNT
           MOVE CHGBK-REC(24:8) TO WS-CHGBK-MERCHANT
           MOVE CHGBK-REC(32:8) TO WS-CHGBK-DATE
           MOVE 0 TO WS-MATCH-IDX

           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > WS-SALE-COUNT
               IF SL-USED(WS-IDX) NOT = "Y"
                  AND SL-ID(WS-IDX) = WS-CHGBK-SALE
                  AND SL-MERCHANT(WS-IDX) = WS-CHGBK-MERCHANT
                  AND SL-AMOUNT(WS-IDX) = WS-CHGBK-AMOUNT
                  AND SL-STATUS(WS-IDX) = "S"
                  AND (SL-REASON(WS-IDX) = "F10"
                       OR SL-REASON(WS-IDX) = "F20"
                       OR SL-REASON(WS-IDX) = "R99"
                       OR SL-REASON(WS-IDX) = "MRC")
                   PERFORM CHECK-DATE-ELIGIBLE
                   IF WS-DATE-ELIGIBLE = "Y"
                       IF WS-MATCH-IDX = 0
                           MOVE WS-IDX TO WS-MATCH-IDX
                       ELSE
                           IF SL-DATE(WS-IDX) > SL-DATE(WS-MATCH-IDX)
                               MOVE WS-IDX TO WS-MATCH-IDX
                           ELSE
                               IF SL-DATE(WS-IDX) = SL-DATE(WS-MATCH-IDX)
                                  AND WS-IDX > WS-MATCH-IDX
                                   MOVE WS-IDX TO WS-MATCH-IDX
                               END-IF
                           END-IF
                       END-IF
                   END-IF
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
           PERFORM WRITE-REPORT-ROW.

       CHECK-DATE-ELIGIBLE.
           MOVE "N" TO WS-DATE-ELIGIBLE
           IF WS-CHGBK-DATE = SPACES
               IF SL-DATE(WS-IDX) = SPACES
                   MOVE "Y" TO WS-DATE-ELIGIBLE
               END-IF
               EXIT PARAGRAPH
           END-IF
           IF SL-DATE(WS-IDX) = SPACES
               EXIT PARAGRAPH
           END-IF
           MOVE SL-DATE(WS-IDX) TO WS-CHECK-DATE
           PERFORM CHECK-DATE-OPEN
           IF WS-DATE-OPEN NOT = "Y"
               EXIT PARAGRAPH
           END-IF
           MOVE WS-CHGBK-DATE TO WS-CHECK-DATE
           PERFORM CHECK-DATE-OPEN
           IF WS-DATE-OPEN NOT = "Y"
               EXIT PARAGRAPH
           END-IF
           IF WS-CHGBK-DATE < SL-DATE(WS-IDX)
               EXIT PARAGRAPH
           END-IF
           MOVE 0 TO WS-OPEN-DAYS
           PERFORM VARYING WS-CAL-IDX FROM 1 BY 1
               UNTIL WS-CAL-IDX > WS-CAL-COUNT
               IF CAL-OPEN(WS-CAL-IDX) = "Y"
                  AND CAL-DATE(WS-CAL-IDX) > SL-DATE(WS-IDX)
                  AND CAL-DATE(WS-CAL-IDX) NOT > WS-CHGBK-DATE
                   ADD 1 TO WS-OPEN-DAYS
               END-IF
           END-PERFORM
           IF WS-OPEN-DAYS NOT > 2
               MOVE "Y" TO WS-DATE-ELIGIBLE
           END-IF.

       CHECK-DATE-OPEN.
           MOVE "N" TO WS-DATE-OPEN
           PERFORM VARYING WS-CAL-IDX FROM 1 BY 1
               UNTIL WS-CAL-IDX > WS-CAL-COUNT
                  OR WS-DATE-OPEN = "Y"
               IF CAL-DATE(WS-CAL-IDX) = WS-CHECK-DATE
                  AND CAL-OPEN(WS-CAL-IDX) = "Y"
                   MOVE "Y" TO WS-DATE-OPEN
               END-IF
           END-PERFORM.

       WRITE-REPORT-ROW.
           MOVE SPACES TO REPORT-REC
           IF WS-MATCH-IDX > 0
               STRING WS-CHGBK-SALE DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-CHGBK-MERCHANT DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   SL-REASON(WS-MATCH-IDX) DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-CHGBK-AMOUNT DELIMITED BY SIZE
                   ",APPLIED" DELIMITED BY SIZE
                   INTO REPORT-REC
               END-STRING
           ELSE
               STRING WS-CHGBK-SALE DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-CHGBK-MERCHANT DELIMITED BY SIZE
                   ",," DELIMITED BY SIZE
                   WS-CHGBK-AMOUNT DELIMITED BY SIZE
                   ",EXCEPTION" DELIMITED BY SIZE
                   INTO REPORT-REC
               END-STRING
           END-IF
           WRITE REPORT-REC.

       WRITE-SUMMARY.
           MOVE SPACES TO SUMMARY-REC
           STRING "applied_count=" DELIMITED BY SIZE
               WS-APPLIED-COUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "applied_amount_cents=" DELIMITED BY SIZE
               WS-APPLIED-AMOUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "exception_count=" DELIMITED BY SIZE
               WS-EXCEPTION-COUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "exception_amount_cents=" DELIMITED BY SIZE
               WS-EXCEPTION-AMOUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC.
''')
PY
/app/scripts/run_batch.sh
test -s /app/out/chargeback_report.csv
test -s /app/out/chargeback_summary.txt
