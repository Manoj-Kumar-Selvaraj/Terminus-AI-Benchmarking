#!/usr/bin/env bash
set -euo pipefail

cat > /app/src/wire_returns.cbl <<'COBOL'
       IDENTIFICATION DIVISION.
       PROGRAM-ID. WIRE-RETURNS.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT WIRE-FILE ASSIGN TO "/app/data/wires.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT RETURN-FILE ASSIGN TO "/app/data/returns.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CALENDAR-FILE ASSIGN TO "/app/config/cycle_calendar.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT REPORT-FILE ASSIGN TO "/app/out/wire_return_report.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUMMARY-FILE ASSIGN TO "/app/out/wire_return_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD WIRE-FILE.
       01 WIRE-REC PIC X(80).
       FD RETURN-FILE.
       01 RETURN-REC PIC X(80).
       FD CALENDAR-FILE.
       01 CALENDAR-REC PIC X(32).
       FD REPORT-FILE.
       01 REPORT-REC PIC X(160).
       FD SUMMARY-FILE.
       01 SUMMARY-REC PIC X(80).

       WORKING-STORAGE SECTION.
       01 WS-EOF-WIRE PIC X VALUE "N".
       01 WS-EOF-RETURN PIC X VALUE "N".
       01 WS-EOF-CALENDAR PIC X VALUE "N".
       01 WS-IDX PIC 9(4) COMP VALUE 0.
       01 WS-CAL-IDX PIC 9(4) COMP VALUE 0.
       01 WS-COUNT-IDX PIC 9(4) COMP VALUE 0.
       01 WS-WIRE-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-CALENDAR-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-MATCH-IDX PIC 9(4) COMP VALUE 0.
       01 WS-CLEARED-COUNT PIC 9(6) VALUE 0.
       01 WS-EXCEPTION-COUNT PIC 9(6) VALUE 0.
       01 WS-CLEARED-AMOUNT PIC 9(12) VALUE 0.
       01 WS-EXCEPTION-AMOUNT PIC 9(12) VALUE 0.
       01 WS-RETURN-WIRE PIC X(12).
       01 WS-RETURN-AMOUNT-TEXT PIC X(10).
       01 WS-RETURN-AMOUNT PIC 9(10).
       01 WS-RETURN-ACCOUNT PIC X(8).
       01 WS-RETURN-DATE PIC X(8).
       01 WS-OPEN-DAYS PIC 9(4) VALUE 0.
       01 WS-WIRE-OPEN PIC X VALUE "N".
       01 WS-RETURN-OPEN PIC X VALUE "N".
       01 WS-DATE-OK PIC X VALUE "N".
       01 WS-WIRES.
          05 WIRE-TABLE OCCURS 250 TIMES.
             10 WR-ID PIC X(12).
             10 WR-REASON PIC X(3).
             10 WR-AMOUNT-TEXT PIC X(10).
             10 WR-AMOUNT PIC 9(10).
             10 WR-ACCOUNT PIC X(8).
             10 WR-STATUS PIC X.
             10 WR-DATE PIC X(8).
             10 WR-USED PIC X.
       01 WS-CALENDAR.
          05 CAL-TABLE OCCURS 500 TIMES.
             10 CAL-DATE PIC X(8).

       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM LOAD-CALENDAR
           OPEN INPUT WIRE-FILE
           PERFORM UNTIL WS-EOF-WIRE = "Y"
               READ WIRE-FILE
                   AT END MOVE "Y" TO WS-EOF-WIRE
                   NOT AT END PERFORM STORE-WIRE
               END-READ
           END-PERFORM
           CLOSE WIRE-FILE

           OPEN INPUT RETURN-FILE
           OPEN OUTPUT REPORT-FILE
           OPEN OUTPUT SUMMARY-FILE
           MOVE "wire_id,account_id,reason,amount_cents,status" TO REPORT-REC
           WRITE REPORT-REC

           PERFORM UNTIL WS-EOF-RETURN = "Y"
               READ RETURN-FILE
                   AT END MOVE "Y" TO WS-EOF-RETURN
                   NOT AT END PERFORM PROCESS-RETURN
               END-READ
           END-PERFORM

           PERFORM WRITE-SUMMARY
           CLOSE RETURN-FILE REPORT-FILE SUMMARY-FILE
           STOP RUN.

       LOAD-CALENDAR.
           OPEN INPUT CALENDAR-FILE
           PERFORM UNTIL WS-EOF-CALENDAR = "Y"
               READ CALENDAR-FILE
                   AT END MOVE "Y" TO WS-EOF-CALENDAR
                   NOT AT END
                       IF CALENDAR-REC(10:4) = "OPEN"
                          OR CALENDAR-REC(10:4) = "open"
                          OR CALENDAR-REC(10:4) = "Open"
                           ADD 1 TO WS-CALENDAR-COUNT
                           MOVE CALENDAR-REC(1:8)
                               TO CAL-DATE(WS-CALENDAR-COUNT)
                       END-IF
               END-READ
           END-PERFORM
           CLOSE CALENDAR-FILE.

       STORE-WIRE.
           ADD 1 TO WS-WIRE-COUNT
           MOVE WIRE-REC(2:12) TO WR-ID(WS-WIRE-COUNT)
           MOVE WIRE-REC(14:3) TO WR-REASON(WS-WIRE-COUNT)
           MOVE WIRE-REC(17:10) TO WR-AMOUNT-TEXT(WS-WIRE-COUNT)
           MOVE WIRE-REC(17:10) TO WR-AMOUNT(WS-WIRE-COUNT)
           MOVE WIRE-REC(27:8) TO WR-ACCOUNT(WS-WIRE-COUNT)
           MOVE WIRE-REC(35:1) TO WR-STATUS(WS-WIRE-COUNT)
           MOVE WIRE-REC(36:8) TO WR-DATE(WS-WIRE-COUNT)
           MOVE "N" TO WR-USED(WS-WIRE-COUNT).

       PROCESS-RETURN.
           MOVE RETURN-REC(2:12) TO WS-RETURN-WIRE
           MOVE RETURN-REC(14:10) TO WS-RETURN-AMOUNT-TEXT
           MOVE RETURN-REC(14:10) TO WS-RETURN-AMOUNT
           MOVE RETURN-REC(24:8) TO WS-RETURN-ACCOUNT
           MOVE RETURN-REC(32:8) TO WS-RETURN-DATE
           MOVE 0 TO WS-MATCH-IDX
           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > WS-WIRE-COUNT
               IF WR-USED(WS-IDX) NOT = "Y"
                  AND WR-ID(WS-IDX) = WS-RETURN-WIRE
                  AND WR-ACCOUNT(WS-IDX) = WS-RETURN-ACCOUNT
                  AND WR-AMOUNT-TEXT(WS-IDX) = WS-RETURN-AMOUNT-TEXT
                  AND WR-STATUS(WS-IDX) = "S"
                  AND (WR-REASON(WS-IDX) = "CON"
                       OR WR-REASON(WS-IDX) = "REF"
                       OR WR-REASON(WS-IDX) = "ADM"
                       OR WR-REASON(WS-IDX) = "B2B")
                   PERFORM CHECK-DATE-ELIGIBLE
                   IF WS-DATE-OK = "Y"
                       IF WS-MATCH-IDX = 0
                          OR WR-DATE(WS-IDX) > WR-DATE(WS-MATCH-IDX)
                           MOVE WS-IDX TO WS-MATCH-IDX
                       END-IF
                   END-IF
               END-IF
           END-PERFORM

           IF WS-MATCH-IDX > 0
               MOVE "Y" TO WR-USED(WS-MATCH-IDX)
               ADD 1 TO WS-CLEARED-COUNT
               ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT
           ELSE
               ADD 1 TO WS-EXCEPTION-COUNT
               ADD WS-RETURN-AMOUNT TO WS-EXCEPTION-AMOUNT
           END-IF
           PERFORM WRITE-REPORT-ROW.

       CHECK-DATE-ELIGIBLE.
           MOVE "N" TO WS-DATE-OK
           MOVE "N" TO WS-WIRE-OPEN
           MOVE "N" TO WS-RETURN-OPEN
           MOVE 0 TO WS-OPEN-DAYS
           IF WR-DATE(WS-IDX) = SPACES OR WS-RETURN-DATE = SPACES
               EXIT PARAGRAPH
           END-IF
           IF WS-RETURN-DATE < WR-DATE(WS-IDX)
               EXIT PARAGRAPH
           END-IF
           PERFORM VARYING WS-CAL-IDX FROM 1 BY 1
               UNTIL WS-CAL-IDX > WS-CALENDAR-COUNT
               IF CAL-DATE(WS-CAL-IDX) = WR-DATE(WS-IDX)
                   MOVE "Y" TO WS-WIRE-OPEN
               END-IF
               IF CAL-DATE(WS-CAL-IDX) = WS-RETURN-DATE
                   MOVE "Y" TO WS-RETURN-OPEN
               END-IF
           END-PERFORM
           IF WS-WIRE-OPEN NOT = "Y" OR WS-RETURN-OPEN NOT = "Y"
               EXIT PARAGRAPH
           END-IF
           PERFORM VARYING WS-COUNT-IDX FROM 1 BY 1
               UNTIL WS-COUNT-IDX > WS-CALENDAR-COUNT
               IF CAL-DATE(WS-COUNT-IDX) > WR-DATE(WS-IDX)
                  AND CAL-DATE(WS-COUNT-IDX) <= WS-RETURN-DATE
                   ADD 1 TO WS-OPEN-DAYS
               END-IF
           END-PERFORM
           IF WS-OPEN-DAYS <= 2
               MOVE "Y" TO WS-DATE-OK
           END-IF.

       WRITE-REPORT-ROW.
           MOVE SPACES TO REPORT-REC
           IF WS-MATCH-IDX > 0
               STRING WS-RETURN-WIRE DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-RETURN-ACCOUNT DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WR-REASON(WS-MATCH-IDX) DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-RETURN-AMOUNT-TEXT DELIMITED BY SIZE
                   ",CLEARED" DELIMITED BY SIZE
                   INTO REPORT-REC
               END-STRING
           ELSE
               STRING WS-RETURN-WIRE DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-RETURN-ACCOUNT DELIMITED BY SIZE
                   ",," DELIMITED BY SIZE
                   WS-RETURN-AMOUNT-TEXT DELIMITED BY SIZE
                   ",EXCEPTION" DELIMITED BY SIZE
                   INTO REPORT-REC
               END-STRING
           END-IF
           WRITE REPORT-REC.

       WRITE-SUMMARY.
           MOVE SPACES TO SUMMARY-REC
           STRING "cleared_count=" DELIMITED BY SIZE
               WS-CLEARED-COUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "cleared_amount_cents=" DELIMITED BY SIZE
               WS-CLEARED-AMOUNT DELIMITED BY SIZE INTO SUMMARY-REC
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
COBOL

/app/scripts/run_batch.sh
test -s /app/out/wire_return_report.csv
test -s /app/out/wire_return_summary.txt
