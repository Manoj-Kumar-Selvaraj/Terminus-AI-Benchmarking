       IDENTIFICATION DIVISION.
       PROGRAM-ID. scooter-surcharge-reconcile.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SRC-FILE ASSIGN TO "/app/data/ride_charges.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT ACT-FILE ASSIGN TO "/app/data/surcharge_reversals.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CAL-FILE ASSIGN TO "/app/config/fleet_calendar.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT REP-FILE ASSIGN TO "/app/out/scooter_surcharge_report.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUM-FILE ASSIGN TO "/app/out/scooter_surcharge_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD SRC-FILE.
       01 SRC-LINE PIC X(80).
       FD ACT-FILE.
       01 ACT-LINE PIC X(80).
       FD CAL-FILE.
       01 CAL-LINE PIC X(80).
       FD REP-FILE.
       01 REP-LINE PIC X(200).
       FD SUM-FILE.
       01 SUM-LINE PIC X(80).
       WORKING-STORAGE SECTION.
       01 EOF-SRC PIC X VALUE "N".
       01 EOF-ACT PIC X VALUE "N".
       01 EOF-CAL PIC X VALUE "N".
       01 SRC-COUNT PIC 9(4) VALUE 0.
       01 CAL-COUNT PIC 9(4) VALUE 0.
       01 I PIC 9(4) VALUE 0.
       01 CAL-IDX PIC 9(4) VALUE 0.
       01 MATCH-IDX PIC 9(4) VALUE 0.
       01 OPEN-FLAG PIC X VALUE "N".
       01 MATCHED-FLAG PIC X VALUE "N".
       01 REASON-OK PIC X VALUE "N".
       01 CHECK-DATE PIC X(8).
       01 CANON-CAT PIC X(3).
       01 WORK-AMOUNT PIC 9(10) VALUE 0.
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
       01 WS-UPPER PIC X(20).
       01 SRC-TABLE.
          05 SRC-ROW OCCURS 200 TIMES.
             10 SRC-ID PIC X(12).
             10 SRC-ACCT PIC X(8).
             10 SRC-CAT PIC X(3).
             10 SRC-AMT PIC X(10).
             10 SRC-DATE PIC X(8).
             10 SRC-STATUS PIC X.
             10 SRC-BRANCH PIC X(4).
             10 SRC-USED PIC X.
       01 CAL-TABLE.
          05 CAL-ROW OCCURS 100 TIMES.
             10 CAL-DATE PIC X(8).
             10 CAL-STATE PIC X(20).
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL "SYSTEM" USING "mkdir -p /app/out"
           PERFORM LOAD-SOURCES
           PERFORM LOAD-CALENDAR
           OPEN INPUT ACT-FILE
           OPEN OUTPUT REP-FILE SUM-FILE
           MOVE SPACES TO REP-LINE
           MOVE "record_id,account,zone_code,amount_cents,reason,status" TO REP-LINE
           WRITE REP-LINE
           PERFORM UNTIL EOF-ACT = "Y"
               READ ACT-FILE
                   AT END MOVE "Y" TO EOF-ACT
                   NOT AT END PERFORM PROCESS-ACTION
               END-READ
           END-PERFORM
           PERFORM WRITE-SUMMARY
           CLOSE ACT-FILE REP-FILE SUM-FILE
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
                       MOVE CAL-LINE(10:20) TO CAL-STATE(CAL-COUNT)
               END-READ
           END-PERFORM
           CLOSE CAL-FILE.

       NORMALIZE-ZONE.
           MOVE ACT-CAT TO CANON-CAT
           MOVE FUNCTION UPPER-CASE(CANON-CAT) TO CANON-CAT
           IF CANON-CAT = "CBD" OR CANON-CAT = "RES" OR CANON-CAT = "UNI"
               EXIT PARAGRAPH
           END-IF
           IF ACT-CAT(1:2) = "CB"
               MOVE "CBD" TO CANON-CAT
           END-IF
           IF ACT-CAT(1:2) = "RE"
               MOVE "RES" TO CANON-CAT
           END-IF
           IF ACT-CAT(1:2) = "UN"
               MOVE "UNI" TO CANON-CAT
           END-IF.

       CHECK-REASON-ELIGIBLE.
           MOVE "N" TO REASON-OK
           MOVE FUNCTION UPPER-CASE(FUNCTION TRIM(ACT-REASON)) TO WS-UPPER
           IF WS-UPPER(1:3) = "S02" OR WS-UPPER(1:3) = "S07"
              OR WS-UPPER(1:3) = "S15"
               MOVE "Y" TO REASON-OK
           END-IF.

       CHECK-CALENDAR-OPEN.
           MOVE "N" TO OPEN-FLAG
           IF CHECK-DATE IS NOT NUMERIC
               EXIT PARAGRAPH
           END-IF
           PERFORM VARYING CAL-IDX FROM 1 BY 1
               UNTIL CAL-IDX > CAL-COUNT OR OPEN-FLAG = "Y"
               IF CAL-DATE(CAL-IDX) = CHECK-DATE
                  AND FUNCTION UPPER-CASE(CAL-STATE(CAL-IDX)) = "OPEN"
                   MOVE "Y" TO OPEN-FLAG
               END-IF
           END-PERFORM.

       PROCESS-ACTION.
           MOVE ACT-LINE(2:12) TO ACT-ID
           MOVE ACT-LINE(14:8) TO ACT-ACCT
           MOVE ACT-LINE(22:3) TO ACT-CAT
           MOVE ACT-LINE(25:10) TO ACT-AMT
           MOVE ACT-LINE(35:8) TO ACT-DATE
           MOVE ACT-LINE(43:3) TO ACT-REASON
           MOVE ACT-LINE(46:4) TO ACT-BRANCH
           PERFORM NORMALIZE-ZONE
           PERFORM CHECK-REASON-ELIGIBLE
           MOVE "N" TO MATCHED-FLAG
           MOVE 0 TO MATCH-IDX
           IF REASON-OK = "Y"
               PERFORM VARYING I FROM 1 BY 1 UNTIL I > SRC-COUNT
                   IF ACT-ID = SRC-ID(I)
                      AND ACT-ACCT = SRC-ACCT(I)
                      AND CANON-CAT = SRC-CAT(I)
                      AND ACT-AMT = SRC-AMT(I)
                      AND SRC-BRANCH(I) = ACT-BRANCH
                      AND SRC-USED(I) NOT = "Y"
                      AND SRC-STATUS(I) = "Z"
                      AND ( SRC-CAT(I) = "CBD"
                     OR SRC-CAT(I) = "RES"
                     OR SRC-CAT(I) = "UNI" )
                      AND ACT-DATE IS NUMERIC
                      AND SRC-DATE(I) IS NUMERIC
                      AND FUNCTION NUMVAL(ACT-DATE) >= FUNCTION NUMVAL(SRC-DATE(I))
                       MOVE SRC-DATE(I) TO CHECK-DATE
                       PERFORM CHECK-CALENDAR-OPEN
                       IF OPEN-FLAG = "Y"
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
                   END-IF
               END-PERFORM
           END-IF
           IF MATCHED-FLAG = "Y"
               MOVE "Y" TO SRC-USED(MATCH-IDX)
           END-IF
           MOVE ACT-AMT TO WORK-AMOUNT
           IF MATCHED-FLAG = "Y"
               ADD 1 TO MATCHED-COUNT
               ADD WORK-AMOUNT TO MATCHED-AMOUNT
               MOVE SPACES TO REP-LINE
               STRING ACT-ID DELIMITED BY SPACE "," ACT-ACCT DELIMITED BY SPACE ","
                      SRC-CAT(MATCH-IDX) DELIMITED BY SPACE "," ACT-AMT DELIMITED BY SIZE ","
                      ACT-REASON DELIMITED BY SPACE ",MATCHED"
                      DELIMITED BY SIZE INTO REP-LINE
               END-STRING
           ELSE
               ADD 1 TO UNMATCHED-COUNT
               ADD WORK-AMOUNT TO UNMATCHED-AMOUNT
               MOVE SPACES TO REP-LINE
               STRING ACT-ID DELIMITED BY SPACE "," ACT-ACCT DELIMITED BY SPACE ",,"
                      ACT-AMT DELIMITED BY SIZE "," ACT-REASON DELIMITED BY SPACE ",UNMATCHED"
                      DELIMITED BY SIZE INTO REP-LINE
               END-STRING
           END-IF
           WRITE REP-LINE.

       WRITE-SUMMARY.
           MOVE SPACES TO SUM-LINE
           STRING "matched_count=" MATCHED-COUNT DELIMITED BY SIZE INTO SUM-LINE END-STRING
           WRITE SUM-LINE
           MOVE SPACES TO SUM-LINE
           STRING "matched_amount_cents=" MATCHED-AMOUNT DELIMITED BY SIZE INTO SUM-LINE END-STRING
           WRITE SUM-LINE
           MOVE SPACES TO SUM-LINE
           STRING "unmatched_count=" UNMATCHED-COUNT DELIMITED BY SIZE INTO SUM-LINE END-STRING
           WRITE SUM-LINE
           MOVE SPACES TO SUM-LINE
           STRING "unmatched_amount_cents=" UNMATCHED-AMOUNT DELIMITED BY SIZE INTO SUM-LINE END-STRING
           WRITE SUM-LINE.
