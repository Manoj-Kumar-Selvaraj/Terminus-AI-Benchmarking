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
           SELECT REASON-FILE ASSIGN TO "/app/config/reason_codes.csv"
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
       01 CALENDAR-REC PIC X(80).
       FD REASON-FILE.
       01 REASON-REC PIC X(80).
       FD REPORT-FILE.
       01 REPORT-REC PIC X(160).
       FD SUMMARY-FILE.
       01 SUMMARY-REC PIC X(80).

       WORKING-STORAGE SECTION.
       01 WS-EOF-WIRE PIC X VALUE "N".
       01 WS-EOF-RETURN PIC X VALUE "N".
       01 WS-EOF-CALENDAR PIC X VALUE "N".
       01 WS-EOF-REASON PIC X VALUE "N".
       01 WS-IDX PIC 9(4) COMP VALUE 0.
       01 WS-CAL-IDX PIC 9(4) COMP VALUE 0.
       01 WS-REASON-IDX PIC 9(4) COMP VALUE 0.
       01 WS-WIRE-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-CAL-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-REASON-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-MATCH-IDX PIC 9(4) COMP VALUE 0.
       01 WS-CLEARED-COUNT PIC 9(6) VALUE 0.
       01 WS-EXCEPTION-COUNT PIC 9(6) VALUE 0.
       01 WS-CLEARED-AMOUNT PIC 9(12) VALUE 0.
       01 WS-EXCEPTION-AMOUNT PIC 9(12) VALUE 0.
       01 WS-CYCLE-DAYS PIC 9(4) VALUE 0.
       01 WS-TARGET-DATE PIC X(8).
       01 WS-DATE-OPEN PIC X VALUE "N".
       01 WS-WIRE-DATE-OPEN PIC X VALUE "N".
       01 WS-RETURN-DATE-OPEN PIC X VALUE "N".
       01 WS-REASON-ALLOWED PIC X VALUE "N".
       01 WS-REASON-CODE PIC X(3).
       01 WS-REASON-FIELD PIC X(24).
       01 WS-RETURN-WIRE PIC X(12).
       01 WS-RETURN-AMOUNT PIC 9(10).
       01 WS-RETURN-ACCOUNT PIC X(8).
       01 WS-RETURN-DATE PIC X(8).
       01 WS-WIRES.
          05 WIRE-TABLE OCCURS 250 TIMES.
             10 WR-ID PIC X(12).
             10 WR-REASON PIC X(3).
             10 WR-AMOUNT PIC 9(10).
             10 WR-ACCOUNT PIC X(8).
             10 WR-STATUS PIC X.
             10 WR-USED PIC X.
             10 WR-DATE PIC X(8).
       01 CALENDAR-TABLE.
          05 CAL-ENTRY OCCURS 200 TIMES.
             10 CAL-DATE PIC X(8).
             10 CAL-OPEN PIC X.
       01 REASON-TABLE.
          05 RC-ENTRY OCCURS 100 TIMES.
             10 RC-CODE PIC X(3).

       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM LOAD-REASON-CODES
           PERFORM LOAD-CALENDAR
           OPEN INPUT WIRE-FILE
           PERFORM UNTIL WS-EOF-WIRE = "Y"
               READ WIRE-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-WIRE
                   NOT AT END
                       PERFORM STORE-WIRE
               END-READ
           END-PERFORM
           CLOSE WIRE-FILE

           OPEN INPUT RETURN-FILE
           OPEN OUTPUT REPORT-FILE
           OPEN OUTPUT SUMMARY-FILE
           MOVE SPACES TO REPORT-REC
           MOVE "wire_id,account_id,reason,amount_cents,status" TO REPORT-REC
           WRITE REPORT-REC

           PERFORM UNTIL WS-EOF-RETURN = "Y"
               READ RETURN-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-RETURN
                   NOT AT END
                       PERFORM PROCESS-RETURN
               END-READ
           END-PERFORM

           PERFORM WRITE-SUMMARY
           CLOSE RETURN-FILE
           CLOSE REPORT-FILE
           CLOSE SUMMARY-FILE
           STOP RUN.

       LOAD-REASON-CODES.
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

       LOAD-CALENDAR.
           OPEN INPUT CALENDAR-FILE
           PERFORM UNTIL WS-EOF-CALENDAR = "Y"
               READ CALENDAR-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-CALENDAR
                   NOT AT END
                       IF CALENDAR-REC(1:8) NOT = SPACES
                           ADD 1 TO WS-CAL-COUNT
                           MOVE CALENDAR-REC(1:8) TO CAL-DATE(WS-CAL-COUNT)
                           IF FUNCTION UPPER-CASE(CALENDAR-REC(10:4)) = "OPEN"
                               MOVE "Y" TO CAL-OPEN(WS-CAL-COUNT)
                           ELSE
                               MOVE "N" TO CAL-OPEN(WS-CAL-COUNT)
                           END-IF
                       END-IF
               END-READ
           END-PERFORM
           CLOSE CALENDAR-FILE.

       STORE-WIRE.
           ADD 1 TO WS-WIRE-COUNT
           MOVE WIRE-REC(2:12) TO WR-ID(WS-WIRE-COUNT)
           MOVE WIRE-REC(14:3) TO WR-REASON(WS-WIRE-COUNT)
           MOVE WIRE-REC(17:10) TO WR-AMOUNT(WS-WIRE-COUNT)
           MOVE WIRE-REC(27:8) TO WR-ACCOUNT(WS-WIRE-COUNT)
           MOVE WIRE-REC(35:1) TO WR-STATUS(WS-WIRE-COUNT)
           MOVE "N" TO WR-USED(WS-WIRE-COUNT)
           MOVE WIRE-REC(36:8) TO WR-DATE(WS-WIRE-COUNT).

       PROCESS-RETURN.
           MOVE RETURN-REC(2:12) TO WS-RETURN-WIRE
           MOVE RETURN-REC(14:10) TO WS-RETURN-AMOUNT
           MOVE RETURN-REC(24:8) TO WS-RETURN-ACCOUNT
           MOVE RETURN-REC(32:8) TO WS-RETURN-DATE
           MOVE 0 TO WS-MATCH-IDX
           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > WS-WIRE-COUNT
               MOVE WR-DATE(WS-IDX) TO WS-TARGET-DATE
               PERFORM CHECK-DATE-OPEN
               MOVE WS-DATE-OPEN TO WS-WIRE-DATE-OPEN
               MOVE WS-RETURN-DATE TO WS-TARGET-DATE
               PERFORM CHECK-DATE-OPEN
               MOVE WS-DATE-OPEN TO WS-RETURN-DATE-OPEN
               PERFORM COUNT-CYCLE-DAYS
               PERFORM CHECK-REASON-ALLOWED
               IF WR-USED(WS-IDX) NOT = "Y"
                  AND WS-WIRE-DATE-OPEN = "Y"
                  AND WS-RETURN-DATE-OPEN = "Y"
                  AND WS-REASON-ALLOWED = "Y"
                  AND WS-RETURN-DATE >= WR-DATE(WS-IDX)
                  AND WS-CYCLE-DAYS <= 2
                  AND WR-ID(WS-IDX) = WS-RETURN-WIRE
                  AND WR-ACCOUNT(WS-IDX) = WS-RETURN-ACCOUNT
                  AND WR-AMOUNT(WS-IDX) = WS-RETURN-AMOUNT
                  AND WR-STATUS(WS-IDX) = "S"
                   IF WS-MATCH-IDX = 0
                       MOVE WS-IDX TO WS-MATCH-IDX
                   ELSE
                       IF WR-DATE(WS-IDX) > WR-DATE(WS-MATCH-IDX)
                           MOVE WS-IDX TO WS-MATCH-IDX
                       END-IF
                   END-IF
               END-IF
           END-PERFORM

           IF WS-MATCH-IDX > 0
               ADD 1 TO WS-CLEARED-COUNT
               ADD WS-RETURN-AMOUNT TO WS-CLEARED-AMOUNT
               MOVE "Y" TO WR-USED(WS-MATCH-IDX)
           ELSE
               ADD 1 TO WS-EXCEPTION-COUNT
               ADD WS-RETURN-AMOUNT TO WS-EXCEPTION-AMOUNT
           END-IF
           PERFORM WRITE-REPORT-ROW.

       CHECK-REASON-ALLOWED.
           MOVE "N" TO WS-REASON-ALLOWED
           PERFORM VARYING WS-REASON-IDX FROM 1 BY 1
               UNTIL WS-REASON-IDX > WS-REASON-COUNT
               IF RC-CODE(WS-REASON-IDX) = WR-REASON(WS-IDX)
                   MOVE "Y" TO WS-REASON-ALLOWED
               END-IF
           END-PERFORM.

       CHECK-DATE-OPEN.
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

       WRITE-REPORT-ROW.
           MOVE SPACES TO REPORT-REC
           IF WS-MATCH-IDX > 0
               STRING WS-RETURN-WIRE DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-RETURN-ACCOUNT DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WR-REASON(WS-MATCH-IDX) DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-RETURN-AMOUNT DELIMITED BY SIZE
                   ",CLEARED" DELIMITED BY SIZE
                   INTO REPORT-REC
               END-STRING
           ELSE
               STRING WS-RETURN-WIRE DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-RETURN-ACCOUNT DELIMITED BY SIZE
                   ",," DELIMITED BY SIZE
                   WS-RETURN-AMOUNT DELIMITED BY SIZE
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
