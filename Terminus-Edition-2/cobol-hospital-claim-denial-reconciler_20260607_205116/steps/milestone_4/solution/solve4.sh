#!/bin/bash
set -euo pipefail
cat > /app/src/claim_denial_reconcile.cbl <<'COBOL'
       IDENTIFICATION DIVISION.
       PROGRAM-ID. claim-denial-reconcile.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SRC-FILE ASSIGN TO "/app/data/claims.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT ACT-FILE ASSIGN TO "/app/data/denials.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CAL-FILE ASSIGN TO "/app/config/adjudication_calendar.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OFAC-FILE ASSIGN TO "/app/config/ofac_screening.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT REP-FILE ASSIGN TO "/app/out/denial_report.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUM-FILE ASSIGN TO "/app/out/denial_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT TRACE-FILE ASSIGN TO "/app/out/source_consumption.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD SRC-FILE.
       01 SRC-LINE PIC X(100).
       FD ACT-FILE.
       01 ACT-LINE PIC X(100).
       FD CAL-FILE.
       01 CAL-LINE PIC X(100).
       FD OFAC-FILE.
       01 OFAC-LINE PIC X(100).
       FD REP-FILE.
       01 REP-LINE PIC X(200).
       FD SUM-FILE.
       01 SUM-LINE PIC X(80).
       FD TRACE-FILE.
       01 TRACE-LINE PIC X(120).
       WORKING-STORAGE SECTION.
       01 EOF-SRC PIC X VALUE "N".
       01 EOF-ACT PIC X VALUE "N".
       01 EOF-CAL PIC X VALUE "N".
       01 EOF-OFAC PIC X VALUE "N".
       01 SRC-COUNT PIC 9(4) VALUE 0.
       01 CAL-COUNT PIC 9(4) VALUE 0.
       01 OFAC-COUNT PIC 9(4) VALUE 0.
       01 I PIC 9(4) VALUE 0.
       01 CAL-IDX PIC 9(4) VALUE 0.
       01 OFAC-IDX PIC 9(4) VALUE 0.
       01 OFAC-MATCH-IDX PIC 9(4) VALUE 0.
       01 MATCH-IDX PIC 9(4) VALUE 0.
       01 OPEN-FLAG PIC X VALUE "N".
       01 OFAC-CLEAR-FLAG PIC X VALUE "N".
       01 MATCHED-FLAG PIC X VALUE "N".
       01 CANON-CAT PIC X(3).
       01 WORK-AMOUNT PIC 9(10) VALUE 0.
       01 TRACE-ROW-NUM PIC 9(4) VALUE 0.
       01 MATCHED-COUNT PIC 9(8) VALUE 0.
       01 UNMATCHED-COUNT PIC 9(8) VALUE 0.
       01 MATCHED-AMOUNT PIC 9(12) VALUE 0.
       01 UNMATCHED-AMOUNT PIC 9(12) VALUE 0.
       01 ACT-ID PIC X(12).
       01 ACT-ACCT PIC X(8).
       01 ACT-CAT PIC X(3).
       01 ACT-AMT PIC X(10).
       01 ACT-DATE PIC X(8).
       01 ACT-REASON PIC X(3).
       01 ACT-BRANCH PIC X(4).
       01 ACT-HOSPITAL PIC X(5).
       01 ACT-STATE PIC X(2).
       01 SRC-TABLE.
          05 SRC-ROW OCCURS 200 TIMES.
             10 SRC-ID PIC X(12).
             10 SRC-ACCT PIC X(8).
             10 SRC-CAT PIC X(3).
             10 SRC-AMT PIC X(10).
             10 SRC-DATE PIC X(8).
             10 SRC-STATUS PIC X.
             10 SRC-BRANCH PIC X(4).
             10 SRC-HOSPITAL PIC X(5).
             10 SRC-STATE PIC X(2).
             10 SRC-DOCS PIC X.
             10 SRC-USED PIC X.
       01 CAL-TABLE.
          05 CAL-ROW OCCURS 100 TIMES.
             10 CAL-DATE PIC X(8).
             10 CAL-STATE PIC X(8).
       01 OFAC-TABLE.
          05 OFAC-ROW OCCURS 200 TIMES.
             10 OFAC-ACCT PIC X(8).
             10 OFAC-HOSPITAL PIC X(5).
             10 OFAC-DECISION PIC X(5).
             10 OFAC-DATE PIC X(8).
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL "SYSTEM" USING "mkdir -p /app/out"
           PERFORM LOAD-SOURCES
           PERFORM LOAD-CALENDAR
           PERFORM LOAD-OFAC
           OPEN INPUT ACT-FILE
           OPEN OUTPUT REP-FILE SUM-FILE TRACE-FILE
           MOVE SPACES TO REP-LINE
           MOVE "record_id,account,service,amount_cents,reason,status"
             TO REP-LINE
           WRITE REP-LINE
           MOVE SPACES TO TRACE-LINE
           MOVE "action_record_id,source_row,source_date" TO TRACE-LINE
           WRITE TRACE-LINE
           PERFORM UNTIL EOF-ACT = "Y"
               READ ACT-FILE
                   AT END MOVE "Y" TO EOF-ACT
                   NOT AT END PERFORM PROCESS-ACTION
               END-READ
           END-PERFORM
           PERFORM WRITE-SUMMARY
           CLOSE ACT-FILE REP-FILE SUM-FILE TRACE-FILE
           STOP RUN.

       LOAD-SOURCES.
           OPEN INPUT SRC-FILE
           PERFORM UNTIL EOF-SRC = "Y"
               READ SRC-FILE
                   AT END MOVE "Y" TO EOF-SRC
                   NOT AT END
                       ADD 1 TO SRC-COUNT
                       MOVE SRC-LINE(2:12) TO SRC-ID(SRC-COUNT)
                       MOVE SRC-LINE(14:8) TO SRC-ACCT(SRC-COUNT)
                       MOVE SRC-LINE(22:3) TO SRC-CAT(SRC-COUNT)
                       MOVE SRC-LINE(25:10) TO SRC-AMT(SRC-COUNT)
                       MOVE SRC-LINE(35:8) TO SRC-DATE(SRC-COUNT)
                       MOVE SRC-LINE(43:1) TO SRC-STATUS(SRC-COUNT)
                       MOVE SRC-LINE(44:4) TO SRC-BRANCH(SRC-COUNT)
                       MOVE SRC-LINE(48:5) TO SRC-HOSPITAL(SRC-COUNT)
                       MOVE SRC-LINE(53:2) TO SRC-STATE(SRC-COUNT)
                       MOVE SRC-LINE(55:1) TO SRC-DOCS(SRC-COUNT)
                       INSPECT SRC-ID(SRC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
                       INSPECT SRC-ACCT(SRC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
                       INSPECT SRC-CAT(SRC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
                       INSPECT SRC-STATUS(SRC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
                       INSPECT SRC-BRANCH(SRC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
                       INSPECT SRC-HOSPITAL(SRC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
                       INSPECT SRC-STATE(SRC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
                       INSPECT SRC-DOCS(SRC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
                       MOVE "N" TO SRC-USED(SRC-COUNT)
               END-READ
           END-PERFORM
           CLOSE SRC-FILE.

       LOAD-CALENDAR.
           OPEN INPUT CAL-FILE
           PERFORM UNTIL EOF-CAL = "Y"
               READ CAL-FILE
                   AT END MOVE "Y" TO EOF-CAL
                   NOT AT END
                       ADD 1 TO CAL-COUNT
                       MOVE CAL-LINE(1:8) TO CAL-DATE(CAL-COUNT)
                       MOVE CAL-LINE(10:8) TO CAL-STATE(CAL-COUNT)
                       INSPECT CAL-STATE(CAL-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
               END-READ
           END-PERFORM
           CLOSE CAL-FILE.

       LOAD-OFAC.
           OPEN INPUT OFAC-FILE
           PERFORM UNTIL EOF-OFAC = "Y"
               READ OFAC-FILE
                   AT END MOVE "Y" TO EOF-OFAC
                   NOT AT END
                       ADD 1 TO OFAC-COUNT
                       MOVE OFAC-LINE(1:8) TO OFAC-ACCT(OFAC-COUNT)
                       MOVE OFAC-LINE(9:5)
                         TO OFAC-HOSPITAL(OFAC-COUNT)
                       MOVE OFAC-LINE(14:5)
                         TO OFAC-DECISION(OFAC-COUNT)
                       MOVE OFAC-LINE(19:8) TO OFAC-DATE(OFAC-COUNT)
                       INSPECT OFAC-ACCT(OFAC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
                       INSPECT OFAC-HOSPITAL(OFAC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
                       INSPECT OFAC-DECISION(OFAC-COUNT)
                         REPLACING ALL LOW-VALUE BY SPACE
               END-READ
           END-PERFORM
           CLOSE OFAC-FILE.

       PROCESS-ACTION.
           MOVE ACT-LINE(2:12) TO ACT-ID
           MOVE ACT-LINE(14:8) TO ACT-ACCT
           MOVE ACT-LINE(22:3) TO ACT-CAT
           MOVE ACT-LINE(25:10) TO ACT-AMT
           MOVE ACT-LINE(35:8) TO ACT-DATE
           MOVE ACT-LINE(43:3) TO ACT-REASON
           MOVE ACT-LINE(46:4) TO ACT-BRANCH
           MOVE ACT-LINE(50:5) TO ACT-HOSPITAL
           MOVE ACT-LINE(55:2) TO ACT-STATE
           INSPECT ACT-ID REPLACING ALL LOW-VALUE BY SPACE
           INSPECT ACT-ACCT REPLACING ALL LOW-VALUE BY SPACE
           INSPECT ACT-CAT REPLACING ALL LOW-VALUE BY SPACE
           INSPECT ACT-REASON REPLACING ALL LOW-VALUE BY SPACE
           INSPECT ACT-BRANCH REPLACING ALL LOW-VALUE BY SPACE
           INSPECT ACT-HOSPITAL REPLACING ALL LOW-VALUE BY SPACE
           INSPECT ACT-STATE REPLACING ALL LOW-VALUE BY SPACE
           MOVE ACT-CAT TO CANON-CAT
           IF ACT-CAT(1:2) = "E1"
               MOVE "ER" TO CANON-CAT
           END-IF
           IF ACT-CAT(1:2) = "LB"
               MOVE "LAB" TO CANON-CAT
           END-IF
           IF ACT-CAT(1:2) = "XR"
               MOVE "IMG" TO CANON-CAT
           END-IF
           PERFORM CHECK-OFAC
           MOVE "N" TO MATCHED-FLAG
           MOVE 0 TO MATCH-IDX
           IF OFAC-CLEAR-FLAG = "Y"
              AND ACT-AMT IS NUMERIC
              AND ACT-DATE IS NUMERIC
               PERFORM VARYING I FROM 1 BY 1 UNTIL I > SRC-COUNT
                   PERFORM CHECK-CALENDAR
                   IF ACT-ID = SRC-ID(I)
                      AND ACT-ACCT = SRC-ACCT(I)
                      AND CANON-CAT = SRC-CAT(I)
                      AND ACT-AMT = SRC-AMT(I)
                      AND ACT-BRANCH = SRC-BRANCH(I)
                      AND ACT-HOSPITAL = SRC-HOSPITAL(I)
                      AND ACT-STATE = SRC-STATE(I)
                      AND SRC-USED(I) NOT = "Y"
                      AND FUNCTION UPPER-CASE(SRC-STATUS(I)) = "A"
                      AND FUNCTION UPPER-CASE(SRC-DOCS(I)) = "Y"
                      AND SRC-AMT(I) IS NUMERIC
                      AND SRC-DATE(I) IS NUMERIC
                      AND OPEN-FLAG = "Y"
                      AND (SRC-CAT(I) = "ER"
                        OR SRC-CAT(I) = "LAB"
                        OR SRC-CAT(I) = "IMG")
                      AND (ACT-REASON = "D01"
                        OR ACT-REASON = "D02"
                        OR ACT-REASON = "D17")
                      AND FUNCTION NUMVAL(ACT-DATE)
                          >= FUNCTION NUMVAL(SRC-DATE(I))
                       IF MATCHED-FLAG = "N"
                           MOVE "Y" TO MATCHED-FLAG
                           MOVE I TO MATCH-IDX
                       ELSE
                           IF FUNCTION NUMVAL(SRC-DATE(I))
                              > FUNCTION NUMVAL(SRC-DATE(MATCH-IDX))
                               MOVE I TO MATCH-IDX
                           ELSE
                               IF SRC-DATE(I) = SRC-DATE(MATCH-IDX)
                                  AND I < MATCH-IDX
                                   MOVE I TO MATCH-IDX
                               END-IF
                           END-IF
                       END-IF
                   END-IF
               END-PERFORM
           END-IF
           IF MATCHED-FLAG = "Y"
               MOVE "Y" TO SRC-USED(MATCH-IDX)
               PERFORM WRITE-TRACE-ROW
           END-IF
           IF ACT-AMT IS NUMERIC
               MOVE ACT-AMT TO WORK-AMOUNT
           ELSE
               MOVE 0 TO WORK-AMOUNT
           END-IF
           PERFORM WRITE-REPORT-ROW.

       CHECK-CALENDAR.
           MOVE "N" TO OPEN-FLAG
           IF SRC-DATE(I) IS NUMERIC
               PERFORM VARYING CAL-IDX FROM 1 BY 1
                 UNTIL CAL-IDX > CAL-COUNT OR OPEN-FLAG = "Y"
                   IF CAL-DATE(CAL-IDX) = SRC-DATE(I)
                      AND FUNCTION UPPER-CASE(CAL-STATE(CAL-IDX))
                          = "OPEN"
                       MOVE "Y" TO OPEN-FLAG
                   END-IF
               END-PERFORM
           END-IF.

       CHECK-OFAC.
           MOVE "N" TO OFAC-CLEAR-FLAG
           MOVE 0 TO OFAC-MATCH-IDX
           IF ACT-DATE IS NUMERIC
               PERFORM VARYING OFAC-IDX FROM 1 BY 1
                 UNTIL OFAC-IDX > OFAC-COUNT
                   IF OFAC-ACCT(OFAC-IDX) = ACT-ACCT
                      AND OFAC-HOSPITAL(OFAC-IDX) = ACT-HOSPITAL
                      AND OFAC-DATE(OFAC-IDX) IS NUMERIC
                      AND FUNCTION NUMVAL(OFAC-DATE(OFAC-IDX))
                          <= FUNCTION NUMVAL(ACT-DATE)
                       IF OFAC-MATCH-IDX = 0
                           MOVE OFAC-IDX TO OFAC-MATCH-IDX
                       ELSE
                           IF FUNCTION NUMVAL(OFAC-DATE(OFAC-IDX))
                              > FUNCTION NUMVAL(
                                  OFAC-DATE(OFAC-MATCH-IDX))
                               MOVE OFAC-IDX TO OFAC-MATCH-IDX
                           END-IF
                       END-IF
                   END-IF
               END-PERFORM
           END-IF
           IF OFAC-MATCH-IDX > 0
              AND FUNCTION UPPER-CASE(
                  OFAC-DECISION(OFAC-MATCH-IDX)) = "CLEAR"
               MOVE "Y" TO OFAC-CLEAR-FLAG
           END-IF.

       WRITE-REPORT-ROW.
           MOVE SPACES TO REP-LINE
           IF MATCHED-FLAG = "Y"
               ADD 1 TO MATCHED-COUNT
               ADD WORK-AMOUNT TO MATCHED-AMOUNT
               STRING ACT-ID DELIMITED BY SPACE
                      "," ACT-ACCT DELIMITED BY SPACE
                      "," SRC-CAT(MATCH-IDX) DELIMITED BY SPACE
                      "," ACT-AMT DELIMITED BY SIZE
                      "," ACT-REASON DELIMITED BY SPACE
                      ",MATCHED" DELIMITED BY SIZE
                      INTO REP-LINE
               END-STRING
           ELSE
               ADD 1 TO UNMATCHED-COUNT
               ADD WORK-AMOUNT TO UNMATCHED-AMOUNT
               STRING ACT-ID DELIMITED BY SPACE
                      "," ACT-ACCT DELIMITED BY SPACE
                      ",," ACT-AMT DELIMITED BY SIZE
                      "," ACT-REASON DELIMITED BY SPACE
                      ",UNMATCHED" DELIMITED BY SIZE
                      INTO REP-LINE
               END-STRING
           END-IF
           WRITE REP-LINE.

       WRITE-TRACE-ROW.
           MOVE MATCH-IDX TO TRACE-ROW-NUM
           MOVE SPACES TO TRACE-LINE
           STRING ACT-ID DELIMITED BY SPACE
                  "," TRACE-ROW-NUM DELIMITED BY SIZE
                  "," SRC-DATE(MATCH-IDX) DELIMITED BY SIZE
                  INTO TRACE-LINE
           END-STRING
           WRITE TRACE-LINE.

       WRITE-SUMMARY.
           MOVE SPACES TO SUM-LINE
           STRING "matched_count=" MATCHED-COUNT DELIMITED BY SIZE
             INTO SUM-LINE END-STRING
           WRITE SUM-LINE
           MOVE SPACES TO SUM-LINE
           STRING "matched_amount_cents=" MATCHED-AMOUNT DELIMITED BY SIZE
             INTO SUM-LINE END-STRING
           WRITE SUM-LINE
           MOVE SPACES TO SUM-LINE
           STRING "unmatched_count=" UNMATCHED-COUNT DELIMITED BY SIZE
             INTO SUM-LINE END-STRING
           WRITE SUM-LINE
           MOVE SPACES TO SUM-LINE
           STRING "unmatched_amount_cents=" UNMATCHED-AMOUNT
             DELIMITED BY SIZE INTO SUM-LINE END-STRING
           WRITE SUM-LINE.
COBOL
/app/scripts/run_batch.sh
