       IDENTIFICATION DIVISION.
       PROGRAM-ID. camp-deposit-reconcile.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SRC-FILE ASSIGN TO "/app/data/site_fees.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT ACT-FILE ASSIGN TO "/app/data/deposit_returns.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CAL-FILE ASSIGN TO "/app/config/season_calendar.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT REASON-FILE ASSIGN TO "/app/config/reasons.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CATEG-FILE ASSIGN TO "/app/config/categories.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT POLICY-FILE ASSIGN TO "/app/config/branch_policies.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT REP-FILE ASSIGN TO "/app/out/camp_deposit_report.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUM-FILE ASSIGN TO "/app/out/camp_deposit_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD SRC-FILE.
       01 SRC-LINE PIC X(80).
       FD ACT-FILE.
       01 ACT-LINE PIC X(80).
       FD CAL-FILE.
       01 CAL-LINE PIC X(80).
       FD REASON-FILE.
       01 REASON-REC PIC X(120).
       FD CATEG-FILE.
       01 CATEG-REC PIC X(120).
       FD POLICY-FILE.
       01 POLICY-REC PIC X(160).
       FD REP-FILE.
       01 REP-LINE PIC X(200).
       FD SUM-FILE.
       01 SUM-LINE PIC X(80).
       WORKING-STORAGE SECTION.
       01 EOF-SRC PIC X VALUE "N".
       01 EOF-ACT PIC X VALUE "N".
       01 EOF-CAL PIC X VALUE "N".
       01 EOF-REASON PIC X VALUE "N".
       01 EOF-CATEG PIC X VALUE "N".
       01 EOF-POLICY PIC X VALUE "N".
       01 SRC-COUNT PIC 9(4) VALUE 0.
       01 CAL-COUNT PIC 9(4) VALUE 0.
       01 REASON-COUNT PIC 9(4) VALUE 0.
       01 CATEG-COUNT PIC 9(4) VALUE 0.
       01 POLICY-COUNT PIC 9(4) VALUE 0.
       01 I PIC 9(4) VALUE 0.
       01 J PIC 9(4) VALUE 0.
       01 CAL-IDX PIC 9(4) VALUE 0.
       01 MATCH-IDX PIC 9(4) VALUE 0.
       01 FOUND-IDX PIC 9(4) VALUE 0.
       01 OPEN-FLAG PIC X VALUE "N".
       01 MATCHED-FLAG PIC X VALUE "N".
       01 REASON-OK PIC X VALUE "N".
       01 CATEG-OK PIC X VALUE "N".
       01 POL-OK PIC X VALUE "N".
       01 CHECK-DATE PIC X(8).
       01 CANON-CAT PIC X(3).
       01 WORK-AMOUNT PIC 9(10) VALUE 0.
       01 AMT-OK PIC X VALUE "N".
       01 WORK-PRIORITY PIC 9(4) VALUE 9999.
       01 WORK-PRI-CUR PIC 9(4) VALUE 9999.
       01 MATCH-PRI PIC 9(4) VALUE 9999.
       01 BEST-SDATE PIC 9(8) VALUE 0.
       01 CUR-SDATE PIC 9(8) VALUE 0.
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
       01 RS-CODE PIC X(20).
       01 RS-ELIG PIC X(20).
       01 RS-RVT PIC X(80).
       01 CG-CODE PIC X(20).
       01 CG-ENABLED PIC X(20).
       01 CG-PRIORITY PIC X(20).
       01 CG-RVT PIC X(60).
       01 PL-BRANCH PIC X(20).
       01 PL-SITE PIC X(20).
       01 PL-MAX PIC X(20).
       01 PL-ENABLED PIC X(20).
       01 PL-ALLOW PIC X(20).
       01 PL-RVT PIC X(40).
       01 WS-UPPER PIC X(20).
       01 WS-TRIM PIC X(20).
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
       01 REASON-TABLE.
          05 REASON-ROW OCCURS 50 TIMES.
             10 REASON-CODE PIC X(3).
             10 REASON-ENABLED PIC X.
       01 CATEG-TABLE.
          05 CATEG-ROW OCCURS 10 TIMES.
             10 CATEG-SITE PIC X(3).
             10 CATEG-ENABLED PIC X.
             10 CATEG-PRIORITY PIC 9(4).
       01 POLICY-TABLE.
          05 POLICY-ROW OCCURS 50 TIMES.
             10 POL-BRANCH PIC X(4).
             10 POL-SITE PIC X(3).
             10 POL-MAX PIC 9(10).
             10 POL-ENABLED PIC X.
             10 POL-ALLOW-ANY PIC X.
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL "SYSTEM" USING "mkdir -p /app/out"
           PERFORM LOAD-SOURCES
           PERFORM LOAD-CALENDAR
           PERFORM LOAD-REASONS
           PERFORM LOAD-CATEGORIES
           PERFORM LOAD-POLICIES
           OPEN INPUT ACT-FILE
           OPEN OUTPUT REP-FILE SUM-FILE
           MOVE SPACES TO REP-LINE
           MOVE "record_id,account,site_class,amount_cents,reason,status" TO REP-LINE
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

       LOAD-REASONS.
           MOVE 0 TO REASON-COUNT
           OPEN INPUT REASON-FILE
           PERFORM UNTIL EOF-REASON = "Y"
               READ REASON-FILE
                   AT END MOVE "Y" TO EOF-REASON
                   NOT AT END PERFORM PARSE-REASON-ROW
               END-READ
           END-PERFORM
           CLOSE REASON-FILE.

       PARSE-REASON-ROW.
           MOVE SPACES TO RS-CODE RS-ELIG RS-RVT
           UNSTRING REASON-REC DELIMITED BY ","
               INTO RS-CODE RS-ELIG RS-RVT
           END-UNSTRING
           MOVE FUNCTION TRIM(RS-CODE) TO WS-TRIM
           MOVE FUNCTION UPPER-CASE(WS-TRIM) TO WS-UPPER
           IF WS-UPPER = "CODE"
               EXIT PARAGRAPH
           END-IF
           IF WS-TRIM = SPACES
               EXIT PARAGRAPH
           END-IF
           MOVE FUNCTION TRIM(RS-ELIG) TO WS-TRIM
           MOVE 0 TO FOUND-IDX
           PERFORM VARYING J FROM 1 BY 1 UNTIL J > REASON-COUNT OR FOUND-IDX > 0
               IF REASON-CODE(J) = WS-UPPER(1:3)
                   MOVE J TO FOUND-IDX
               END-IF
           END-PERFORM
           IF FOUND-IDX = 0
               ADD 1 TO REASON-COUNT
               MOVE REASON-COUNT TO FOUND-IDX
               MOVE WS-UPPER(1:3) TO REASON-CODE(FOUND-IDX)
           END-IF
           IF FUNCTION UPPER-CASE(WS-TRIM) = "Y"
               MOVE "Y" TO REASON-ENABLED(FOUND-IDX)
           ELSE
               MOVE "N" TO REASON-ENABLED(FOUND-IDX)
           END-IF.

       LOAD-CATEGORIES.
           MOVE 0 TO CATEG-COUNT
           OPEN INPUT CATEG-FILE
           PERFORM UNTIL EOF-CATEG = "Y"
               READ CATEG-FILE
                   AT END MOVE "Y" TO EOF-CATEG
                   NOT AT END PERFORM PARSE-CATEG-ROW
               END-READ
           END-PERFORM
           CLOSE CATEG-FILE.

       PARSE-CATEG-ROW.
           MOVE SPACES TO CG-CODE CG-ENABLED CG-PRIORITY CG-RVT
           UNSTRING CATEG-REC DELIMITED BY ","
               INTO CG-CODE CG-ENABLED CG-PRIORITY CG-RVT
           END-UNSTRING
           MOVE FUNCTION TRIM(CG-CODE) TO WS-TRIM
           MOVE FUNCTION UPPER-CASE(WS-TRIM) TO WS-UPPER
           IF WS-UPPER = "CODE"
               EXIT PARAGRAPH
           END-IF
           IF WS-TRIM = SPACES
               EXIT PARAGRAPH
           END-IF
           IF WS-UPPER NOT = "TNT" AND WS-UPPER NOT = "RV"
              AND WS-UPPER NOT = "CBN"
               EXIT PARAGRAPH
           END-IF
           MOVE FUNCTION TRIM(CG-ENABLED) TO WS-TRIM
           MOVE FUNCTION UPPER-CASE(WS-TRIM) TO WS-TRIM
           IF WS-TRIM NOT = "TRUE" AND WS-TRIM NOT = "FALSE"
               EXIT PARAGRAPH
           END-IF
           MOVE 0 TO FOUND-IDX
           PERFORM VARYING J FROM 1 BY 1 UNTIL J > CATEG-COUNT OR FOUND-IDX > 0
               IF CATEG-SITE(J) = WS-UPPER(1:3)
                   MOVE J TO FOUND-IDX
               END-IF
           END-PERFORM
           IF FOUND-IDX = 0
               ADD 1 TO CATEG-COUNT
               MOVE CATEG-COUNT TO FOUND-IDX
               MOVE WS-UPPER(1:3) TO CATEG-SITE(FOUND-IDX)
           END-IF
           IF WS-TRIM = "TRUE"
               MOVE "Y" TO CATEG-ENABLED(FOUND-IDX)
           ELSE
               MOVE "N" TO CATEG-ENABLED(FOUND-IDX)
           END-IF
           MOVE FUNCTION TRIM(CG-PRIORITY) TO WS-TRIM
           IF FUNCTION TEST-NUMVAL(FUNCTION TRIM(CG-PRIORITY)) = 0
               MOVE FUNCTION NUMVAL(FUNCTION TRIM(CG-PRIORITY))
                   TO CATEG-PRIORITY(FOUND-IDX)
           ELSE
               MOVE 9999 TO CATEG-PRIORITY(FOUND-IDX)
           END-IF.

       LOAD-POLICIES.
           MOVE 0 TO POLICY-COUNT
           OPEN INPUT POLICY-FILE
           PERFORM UNTIL EOF-POLICY = "Y"
               READ POLICY-FILE
                   AT END MOVE "Y" TO EOF-POLICY
                   NOT AT END PERFORM PARSE-POLICY-ROW
               END-READ
           END-PERFORM
           CLOSE POLICY-FILE.

       PARSE-POLICY-ROW.
           MOVE SPACES TO PL-BRANCH PL-SITE PL-MAX PL-ENABLED PL-ALLOW PL-RVT
           UNSTRING POLICY-REC DELIMITED BY ","
               INTO PL-BRANCH PL-SITE PL-MAX PL-ENABLED PL-ALLOW PL-RVT
           END-UNSTRING
           MOVE FUNCTION TRIM(PL-BRANCH) TO WS-TRIM
           MOVE FUNCTION UPPER-CASE(WS-TRIM) TO WS-UPPER
           IF WS-UPPER = "BRANCH"
               EXIT PARAGRAPH
           END-IF
           IF WS-TRIM = SPACES
               EXIT PARAGRAPH
           END-IF
           MOVE FUNCTION TRIM(PL-SITE) TO WS-TRIM
           MOVE FUNCTION UPPER-CASE(WS-TRIM) TO WS-UPPER
           IF WS-UPPER NOT = "TNT" AND WS-UPPER NOT = "RV"
              AND WS-UPPER NOT = "CBN"
               EXIT PARAGRAPH
           END-IF
           MOVE FUNCTION TRIM(PL-MAX) TO WS-TRIM
           IF FUNCTION TEST-NUMVAL(FUNCTION TRIM(PL-MAX)) NOT = 0
               EXIT PARAGRAPH
           END-IF
           MOVE FUNCTION NUMVAL(FUNCTION TRIM(PL-MAX)) TO WORK-AMOUNT
           IF WORK-AMOUNT <= 0
               EXIT PARAGRAPH
           END-IF
           MOVE FUNCTION TRIM(PL-ENABLED) TO WS-TRIM
           MOVE FUNCTION UPPER-CASE(WS-TRIM) TO WS-TRIM
           IF WS-TRIM NOT = "TRUE" AND WS-TRIM NOT = "FALSE"
               EXIT PARAGRAPH
           END-IF
           MOVE FUNCTION TRIM(PL-ALLOW) TO WS-TRIM
           MOVE FUNCTION UPPER-CASE(WS-TRIM) TO WS-TRIM
           IF WS-TRIM NOT = "TRUE" AND WS-TRIM NOT = "FALSE"
               EXIT PARAGRAPH
           END-IF
           MOVE 0 TO FOUND-IDX
           PERFORM VARYING J FROM 1 BY 1 UNTIL J > POLICY-COUNT OR FOUND-IDX > 0
               IF POL-BRANCH(J) = FUNCTION TRIM(PL-BRANCH)
                  AND POL-SITE(J) = WS-UPPER(1:3)
                   MOVE J TO FOUND-IDX
               END-IF
           END-PERFORM
           IF FOUND-IDX = 0
               ADD 1 TO POLICY-COUNT
               MOVE POLICY-COUNT TO FOUND-IDX
               MOVE FUNCTION TRIM(PL-BRANCH) TO POL-BRANCH(FOUND-IDX)
               MOVE WS-UPPER(1:3) TO POL-SITE(FOUND-IDX)
           END-IF
           MOVE WORK-AMOUNT TO POL-MAX(FOUND-IDX)
           MOVE FUNCTION TRIM(PL-ENABLED) TO WS-TRIM
           MOVE FUNCTION UPPER-CASE(WS-TRIM) TO WS-TRIM
           IF WS-TRIM = "TRUE"
               MOVE "Y" TO POL-ENABLED(FOUND-IDX)
           ELSE
               MOVE "N" TO POL-ENABLED(FOUND-IDX)
           END-IF
           MOVE FUNCTION TRIM(PL-ALLOW) TO WS-TRIM
           MOVE FUNCTION UPPER-CASE(WS-TRIM) TO WS-TRIM
           IF WS-TRIM = "TRUE"
               MOVE "Y" TO POL-ALLOW-ANY(FOUND-IDX)
           ELSE
               MOVE "N" TO POL-ALLOW-ANY(FOUND-IDX)
           END-IF.

       CHECK-BRANCH-POLICY.
           MOVE "N" TO POL-OK
           MOVE 0 TO FOUND-IDX
           PERFORM VARYING J FROM 1 BY 1 UNTIL J > POLICY-COUNT OR FOUND-IDX > 0
               IF POL-BRANCH(J) = ACT-BRANCH
                  AND POL-SITE(J) = SRC-CAT(I)
                   MOVE J TO FOUND-IDX
               END-IF
           END-PERFORM
           IF FOUND-IDX = 0
               EXIT PARAGRAPH
           END-IF
           IF POL-ENABLED(FOUND-IDX) NOT = "Y"
               EXIT PARAGRAPH
           END-IF
           MOVE FUNCTION NUMVAL(FUNCTION TRIM(ACT-AMT)) TO WORK-AMOUNT
           IF WORK-AMOUNT > POL-MAX(FOUND-IDX)
               EXIT PARAGRAPH
           END-IF
           IF CANON-CAT = "ANY"
              AND POL-ALLOW-ANY(FOUND-IDX) NOT = "Y"
               EXIT PARAGRAPH
           END-IF
           MOVE "Y" TO POL-OK.

       NORMALIZE-SITE.
           MOVE FUNCTION UPPER-CASE(FUNCTION TRIM(ACT-CAT)) TO CANON-CAT
           IF CANON-CAT = "ANY"
               EXIT PARAGRAPH
           END-IF
           IF CANON-CAT = "TNT" OR CANON-CAT = "RV" OR CANON-CAT = "CBN"
               EXIT PARAGRAPH
           END-IF
           IF CANON-CAT(1:2) = "NT"
               MOVE "TNT" TO CANON-CAT
           END-IF
           IF CANON-CAT(1:2) = "R0"
               MOVE "RV" TO CANON-CAT
           END-IF
           IF CANON-CAT(1:2) = "CB"
               MOVE "CBN" TO CANON-CAT
           END-IF.

       CHECK-REASON-ELIGIBLE.
           MOVE "N" TO REASON-OK
           MOVE FUNCTION UPPER-CASE(FUNCTION TRIM(ACT-REASON)) TO WS-UPPER
           PERFORM VARYING J FROM 1 BY 1 UNTIL J > REASON-COUNT
               IF REASON-CODE(J) = WS-UPPER(1:3)
                  AND REASON-ENABLED(J) = "Y"
                   MOVE "Y" TO REASON-OK
               END-IF
           END-PERFORM.

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

       CHECK-SOURCE-CATEGORY.
           MOVE "N" TO CATEG-OK
           MOVE 0 TO FOUND-IDX
           PERFORM VARYING J FROM 1 BY 1 UNTIL J > CATEG-COUNT OR FOUND-IDX > 0
               IF CATEG-SITE(J) = SRC-CAT(I)
                   MOVE J TO FOUND-IDX
               END-IF
           END-PERFORM
           IF FOUND-IDX = 0
               EXIT PARAGRAPH
           END-IF
           IF CATEG-ENABLED(FOUND-IDX) = "Y"
               MOVE "Y" TO CATEG-OK
               MOVE CATEG-PRIORITY(FOUND-IDX) TO WORK-PRI-CUR
           END-IF.

       CHECK-ACTION-AMOUNT.
           MOVE "N" TO AMT-OK
           IF ACT-AMT IS NUMERIC
               MOVE FUNCTION NUMVAL(ACT-AMT) TO WORK-AMOUNT
               IF WORK-AMOUNT > 0
                   MOVE "Y" TO AMT-OK
               END-IF
           END-IF.

       PROCESS-ACTION.
           MOVE ACT-LINE(2:12) TO ACT-ID
           MOVE ACT-LINE(14:8) TO ACT-ACCT
           MOVE ACT-LINE(22:3) TO ACT-CAT
           MOVE ACT-LINE(25:10) TO ACT-AMT
           MOVE ACT-LINE(35:8) TO ACT-DATE
           MOVE ACT-LINE(43:3) TO ACT-REASON
           MOVE ACT-LINE(46:4) TO ACT-BRANCH
           PERFORM NORMALIZE-SITE
           PERFORM CHECK-REASON-ELIGIBLE
           PERFORM CHECK-ACTION-AMOUNT
           MOVE "N" TO MATCHED-FLAG
           MOVE 0 TO MATCH-IDX
           IF REASON-OK = "Y" AND AMT-OK = "Y"
               PERFORM VARYING I FROM 1 BY 1 UNTIL I > SRC-COUNT
                   IF ACT-ID = SRC-ID(I)
                      AND ACT-ACCT = SRC-ACCT(I)
                      AND ( CANON-CAT = "ANY" OR CANON-CAT = SRC-CAT(I) )
                      AND ACT-AMT = SRC-AMT(I)
                      AND SRC-BRANCH(I) = ACT-BRANCH
                      AND SRC-USED(I) NOT = "Y"
                      AND SRC-STATUS(I) = "G"
                      AND ( SRC-CAT(I) = "TNT"
                     OR SRC-CAT(I) = "RV"
                     OR SRC-CAT(I) = "CBN" )
                      AND ACT-DATE IS NUMERIC
                      AND SRC-DATE(I) IS NUMERIC
                      AND FUNCTION NUMVAL(ACT-DATE) >= FUNCTION NUMVAL(SRC-DATE(I))
                       MOVE SRC-DATE(I) TO CHECK-DATE
                       PERFORM CHECK-CALENDAR-OPEN
                       IF OPEN-FLAG = "Y"
                           MOVE "N" TO CATEG-OK
                           MOVE 9999 TO WORK-PRI-CUR
                           MOVE 0 TO FOUND-IDX
                           PERFORM VARYING J FROM 1 BY 1
                               UNTIL J > CATEG-COUNT OR FOUND-IDX > 0
                               IF CATEG-SITE(J) = SRC-CAT(I)
                                   MOVE J TO FOUND-IDX
                               END-IF
                           END-PERFORM
                           IF FOUND-IDX > 0
                              AND CATEG-ENABLED(FOUND-IDX) = "Y"
                               MOVE "Y" TO CATEG-OK
                               MOVE CATEG-PRIORITY(FOUND-IDX)
                                   TO WORK-PRI-CUR
                           END-IF
                           IF CATEG-OK = "Y"
                               PERFORM CHECK-BRANCH-POLICY
                               IF POL-OK = "Y"
                               MOVE FUNCTION NUMVAL(SRC-DATE(I)) TO CUR-SDATE
                               IF MATCHED-FLAG = "N"
                                   MOVE "Y" TO MATCHED-FLAG
                                   MOVE I TO MATCH-IDX
                                   MOVE CUR-SDATE TO BEST-SDATE
                                   MOVE WORK-PRI-CUR TO MATCH-PRI
                               ELSE
                                   IF CUR-SDATE > BEST-SDATE
                                       MOVE I TO MATCH-IDX
                                       MOVE CUR-SDATE TO BEST-SDATE
                                       MOVE WORK-PRI-CUR TO MATCH-PRI
                                   ELSE
                                       IF CUR-SDATE = BEST-SDATE
                                           IF WORK-PRI-CUR < MATCH-PRI
                                               MOVE I TO MATCH-IDX
                                               MOVE WORK-PRI-CUR TO MATCH-PRI
                                           ELSE
                                               IF WORK-PRI-CUR = MATCH-PRI
                                                  AND I < MATCH-IDX
                                                   MOVE I TO MATCH-IDX
                                               END-IF
                                           END-IF
                                       END-IF
                                   END-IF
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
           MOVE 0 TO WORK-AMOUNT
           IF AMT-OK = "Y"
               MOVE FUNCTION NUMVAL(ACT-AMT) TO WORK-AMOUNT
           END-IF
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
