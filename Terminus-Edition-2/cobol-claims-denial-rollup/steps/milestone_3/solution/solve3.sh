#!/usr/bin/env bash
set -euo pipefail

cd /app

cat > /app/src/claim_rollup.cbl <<'CBL'
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLAIM-ROLLUP.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CLAIM-FILE ASSIGN TO "/app/data/claims.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT ADJ-FILE ASSIGN TO "/app/data/adjustments.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CAL-FILE ASSIGN TO "/app/config/cycle_calendar.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT REPORT-FILE ASSIGN TO "/app/out/denial_report.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUMMARY-FILE ASSIGN TO "/app/out/denial_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD CLAIM-FILE.
       01 CLAIM-REC PIC X(64).
       FD ADJ-FILE.
       01 ADJ-REC PIC X(64).
       FD CAL-FILE.
       01 CAL-REC PIC X(32).
       FD REPORT-FILE.
       01 REPORT-REC PIC X(160).
       FD SUMMARY-FILE.
       01 SUMMARY-REC PIC X(80).

       WORKING-STORAGE SECTION.
       01 WS-EOF-CLAIM PIC X VALUE "N".
       01 WS-EOF-ADJ PIC X VALUE "N".
       01 WS-EOF-CAL PIC X VALUE "N".
       01 WS-IDX PIC 9(4) COMP VALUE 0.
       01 WS-CAL-IDX PIC 9(4) COMP VALUE 0.
       01 WS-CLAIM-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-CAL-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-MATCH-IDX PIC 9(4) COMP VALUE 0.
       01 WS-MATCHED-COUNT PIC 9(6) VALUE 0.
       01 WS-UNMATCHED-COUNT PIC 9(6) VALUE 0.
       01 WS-MATCHED-AMOUNT PIC S9(12) SIGN LEADING SEPARATE VALUE 0.
       01 WS-UNMATCHED-AMOUNT PIC 9(12) VALUE 0.
       01 WS-DATE-FOUND PIC X VALUE "N".
       01 WS-TARGET-DATE PIC X(8).
       01 WS-DATE-OPEN PIC X VALUE "N".
       01 WS-CAL-STATUS PIC X(6).

       01 WS-ADJ-CLAIM PIC X(12).
       01 WS-ADJ-AMOUNT-TEXT PIC X(10).
       01 WS-ADJ-AMOUNT PIC 9(10).
       01 WS-ADJ-MEMBER PIC X(8).

       01 CALENDAR-TABLE.
          05 CAL-ENTRY OCCURS 200 TIMES.
             10 CAL-DATE PIC X(8).
             10 CAL-OPEN PIC X.

       01 WS-CLAIMS.
          05 CLAIM-TABLE OCCURS 300 TIMES.
             10 CLM-ID PIC X(12).
             10 CLM-REASON PIC X(3).
             10 CLM-AMOUNT PIC 9(10).
             10 CLM-MEMBER PIC X(8).
             10 CLM-STATUS PIC X.
             10 CLM-USED PIC X.

       PROCEDURE DIVISION.
       MAIN-PARA.
           PERFORM LOAD-CALENDAR
           PERFORM LOAD-CLAIMS
           OPEN INPUT ADJ-FILE
           OPEN OUTPUT REPORT-FILE
           OPEN OUTPUT SUMMARY-FILE
           MOVE SPACES TO REPORT-REC
           MOVE "claim_id,member_id,reason,amount_cents,status" TO REPORT-REC
           WRITE REPORT-REC

           PERFORM UNTIL WS-EOF-ADJ = "Y"
               READ ADJ-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-ADJ
                   NOT AT END
                       PERFORM PROCESS-ADJUSTMENT
               END-READ
           END-PERFORM

           PERFORM WRITE-SUMMARY
           CLOSE ADJ-FILE
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
                       IF CAL-REC(1:8) NOT = SPACES
                           MOVE FUNCTION UPPER-CASE(CAL-REC(10:6))
                               TO WS-CAL-STATUS
                           MOVE "N" TO WS-DATE-FOUND
                           PERFORM VARYING WS-CAL-IDX FROM 1 BY 1
                               UNTIL WS-CAL-IDX > WS-CAL-COUNT
                               IF CAL-DATE(WS-CAL-IDX) = CAL-REC(1:8)
                                   MOVE "Y" TO WS-DATE-FOUND
                                   IF WS-CAL-STATUS(1:4) = "OPEN"
                                       MOVE "Y" TO CAL-OPEN(WS-CAL-IDX)
                                   ELSE
                                       MOVE "N" TO CAL-OPEN(WS-CAL-IDX)
                                   END-IF
                               END-IF
                           END-PERFORM
                           IF WS-DATE-FOUND NOT = "Y"
                               ADD 1 TO WS-CAL-COUNT
                               MOVE CAL-REC(1:8) TO CAL-DATE(WS-CAL-COUNT)
                               IF WS-CAL-STATUS(1:4) = "OPEN"
                                   MOVE "Y" TO CAL-OPEN(WS-CAL-COUNT)
                               ELSE
                                   MOVE "N" TO CAL-OPEN(WS-CAL-COUNT)
                               END-IF
                           END-IF
                       END-IF
               END-READ
           END-PERFORM
           CLOSE CAL-FILE.

       LOAD-CLAIMS.
           OPEN INPUT CLAIM-FILE
           PERFORM UNTIL WS-EOF-CLAIM = "Y"
               READ CLAIM-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-CLAIM
                   NOT AT END
                       IF CLAIM-REC(1:1) = "C"
                           PERFORM STORE-CLAIM
                       END-IF
               END-READ
           END-PERFORM
           CLOSE CLAIM-FILE.

       STORE-CLAIM.
           ADD 1 TO WS-CLAIM-COUNT
           MOVE CLAIM-REC(2:12) TO CLM-ID(WS-CLAIM-COUNT)
           MOVE CLAIM-REC(14:3) TO CLM-REASON(WS-CLAIM-COUNT)
           PERFORM NORMALIZE-CLAIM-REASON
           MOVE CLAIM-REC(17:10) TO CLM-AMOUNT(WS-CLAIM-COUNT)
           MOVE CLAIM-REC(27:8) TO CLM-MEMBER(WS-CLAIM-COUNT)
           MOVE CLAIM-REC(35:1) TO CLM-STATUS(WS-CLAIM-COUNT)
           MOVE "N" TO CLM-USED(WS-CLAIM-COUNT).

       NORMALIZE-CLAIM-REASON.
           IF CLM-REASON(WS-CLAIM-COUNT) = "BIL"
               MOVE "COB" TO CLM-REASON(WS-CLAIM-COUNT)
           ELSE
               IF CLM-REASON(WS-CLAIM-COUNT) = "AUN"
                   MOVE "AUT" TO CLM-REASON(WS-CLAIM-COUNT)
               ELSE
                   IF CLM-REASON(WS-CLAIM-COUNT) = "CLN"
                       MOVE "NEC" TO CLM-REASON(WS-CLAIM-COUNT)
                   END-IF
               END-IF
           END-IF.

       PROCESS-ADJUSTMENT.
           MOVE ADJ-REC(2:12) TO WS-ADJ-CLAIM
           MOVE ADJ-REC(14:10) TO WS-ADJ-AMOUNT-TEXT
           MOVE ADJ-REC(14:10) TO WS-ADJ-AMOUNT
           MOVE ADJ-REC(24:8) TO WS-ADJ-MEMBER
           PERFORM FIND-MATCH
           IF WS-MATCH-IDX > 0
               ADD 1 TO WS-MATCHED-COUNT
               ADD WS-ADJ-AMOUNT TO WS-MATCHED-AMOUNT
               MOVE "Y" TO CLM-USED(WS-MATCH-IDX)
           ELSE
               ADD 1 TO WS-UNMATCHED-COUNT
               ADD WS-ADJ-AMOUNT TO WS-UNMATCHED-AMOUNT
           END-IF
           PERFORM WRITE-REPORT-ROW.

       FIND-MATCH.
           MOVE 0 TO WS-MATCH-IDX
           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > WS-CLAIM-COUNT OR WS-MATCH-IDX > 0
               MOVE CLM-ID(WS-IDX)(4:8) TO WS-TARGET-DATE
               PERFORM CHECK-DATE-OPEN
               IF CLM-USED(WS-IDX) NOT = "Y"
                  AND WS-DATE-OPEN = "Y"
                  AND CLM-ID(WS-IDX) = WS-ADJ-CLAIM
                  AND CLM-MEMBER(WS-IDX) = WS-ADJ-MEMBER
                  AND CLM-AMOUNT(WS-IDX) = WS-ADJ-AMOUNT
                  AND CLM-STATUS(WS-IDX) = "D"
                  AND (CLM-REASON(WS-IDX) = "MED"
                       OR CLM-REASON(WS-IDX) = "NEC"
                       OR CLM-REASON(WS-IDX) = "COB"
                       OR CLM-REASON(WS-IDX) = "AUT")
                   MOVE WS-IDX TO WS-MATCH-IDX
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

       WRITE-REPORT-ROW.
           MOVE SPACES TO REPORT-REC
           IF WS-MATCH-IDX > 0
               STRING
                   WS-ADJ-CLAIM DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-ADJ-MEMBER DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   CLM-REASON(WS-MATCH-IDX) DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-ADJ-AMOUNT-TEXT DELIMITED BY SIZE
                   ",MATCHED" DELIMITED BY SIZE
                   INTO REPORT-REC
               END-STRING
           ELSE
               STRING
                   WS-ADJ-CLAIM DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-ADJ-MEMBER DELIMITED BY SIZE
                   ",," DELIMITED BY SIZE
                   WS-ADJ-AMOUNT-TEXT DELIMITED BY SIZE
                   ",UNMATCHED" DELIMITED BY SIZE
                   INTO REPORT-REC
               END-STRING
           END-IF
           WRITE REPORT-REC.

       WRITE-SUMMARY.
           MOVE SPACES TO SUMMARY-REC
           STRING "matched_count=" DELIMITED BY SIZE
               WS-MATCHED-COUNT DELIMITED BY SIZE
               INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "matched_amount_cents=" DELIMITED BY SIZE
               WS-MATCHED-AMOUNT DELIMITED BY SIZE
               INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "unmatched_count=" DELIMITED BY SIZE
               WS-UNMATCHED-COUNT DELIMITED BY SIZE
               INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "unmatched_amount_cents=" DELIMITED BY SIZE
               WS-UNMATCHED-AMOUNT DELIMITED BY SIZE
               INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC.
CBL

/app/scripts/run_batch.sh
test -s /app/out/denial_report.csv
test -s /app/out/denial_summary.txt
