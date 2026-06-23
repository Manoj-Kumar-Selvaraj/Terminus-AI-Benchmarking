       IDENTIFICATION DIVISION.
       PROGRAM-ID. DRAFT-RETURNS.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT DRAFT-FILE ASSIGN TO "/app/data/drafts.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT RETURN-FILE ASSIGN TO "/app/data/returns.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT REPORT-FILE ASSIGN TO "/app/out/draft_return_report.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUMMARY-FILE ASSIGN TO "/app/out/draft_return_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD DRAFT-FILE.
       01 DRAFT-REC PIC X(64).
       FD RETURN-FILE.
       01 RETURN-REC PIC X(64).
       FD REPORT-FILE.
       01 REPORT-REC PIC X(160).
       FD SUMMARY-FILE.
       01 SUMMARY-REC PIC X(80).

       WORKING-STORAGE SECTION.
       01 WS-EOF-DRAFT PIC X VALUE "N".
       01 WS-EOF-RETURN PIC X VALUE "N".
       01 WS-IDX PIC 9(4) COMP VALUE 0.
       01 WS-DRAFT-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-MATCH-IDX PIC 9(4) COMP VALUE 0.
       01 WS-CLEARED-COUNT PIC 9(6) VALUE 0.
       01 WS-EXCEPTION-COUNT PIC 9(6) VALUE 0.
       01 WS-CLEARED-AMOUNT PIC S9(12) SIGN LEADING SEPARATE VALUE 0.
       01 WS-EXCEPTION-AMOUNT PIC 9(12) VALUE 0.
       01 WS-RETURN-DRAFT PIC X(12).
       01 WS-RETURN-AMOUNT PIC 9(10).
       01 WS-RETURN-ACCOUNT PIC X(8).
       01 WS-DRAFTS.
          05 DRAFT-TABLE OCCURS 250 TIMES.
             10 WR-ID PIC X(12).
             10 WR-REASON PIC X(3).
             10 WR-AMOUNT PIC 9(10).
             10 WR-ACCOUNT PIC X(8).
             10 WR-STATUS PIC X.

       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN INPUT DRAFT-FILE
           PERFORM UNTIL WS-EOF-DRAFT = "Y"
               READ DRAFT-FILE
                   AT END
                       MOVE "Y" TO WS-EOF-DRAFT
                   NOT AT END
                       PERFORM STORE-DRAFT
               END-READ
           END-PERFORM
           CLOSE DRAFT-FILE

           OPEN INPUT RETURN-FILE
           OPEN OUTPUT REPORT-FILE
           OPEN OUTPUT SUMMARY-FILE
           MOVE SPACES TO REPORT-REC
           MOVE "draft_id,account_id,reason,amount_cents,status" TO REPORT-REC
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

       STORE-DRAFT.
           ADD 1 TO WS-DRAFT-COUNT
           MOVE DRAFT-REC(2:12) TO WR-ID(WS-DRAFT-COUNT)
           MOVE DRAFT-REC(14:3) TO WR-REASON(WS-DRAFT-COUNT)
           MOVE DRAFT-REC(17:10) TO WR-AMOUNT(WS-DRAFT-COUNT)
           MOVE DRAFT-REC(27:8) TO WR-ACCOUNT(WS-DRAFT-COUNT)
           MOVE DRAFT-REC(35:1) TO WR-STATUS(WS-DRAFT-COUNT).

       PROCESS-RETURN.
           MOVE RETURN-REC(2:12) TO WS-RETURN-DRAFT
           MOVE RETURN-REC(14:10) TO WS-RETURN-AMOUNT
           MOVE RETURN-REC(24:8) TO WS-RETURN-ACCOUNT
           MOVE 0 TO WS-MATCH-IDX
           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > WS-DRAFT-COUNT OR WS-MATCH-IDX > 0
               IF WR-ID(WS-IDX)(1:10) = WS-RETURN-DRAFT(1:10)
                  AND WR-ACCOUNT(WS-IDX) = WS-RETURN-ACCOUNT
                  AND WR-AMOUNT(WS-IDX) = WS-RETURN-AMOUNT
                  AND WR-STATUS(WS-IDX) = "S"
                  AND (WR-REASON(WS-IDX) = "CON"
                       OR WR-REASON(WS-IDX) = "REF"
                       OR WR-REASON(WS-IDX) = "ADM")
                   MOVE WS-IDX TO WS-MATCH-IDX
               END-IF
           END-PERFORM

           IF WS-MATCH-IDX > 0
               ADD 1 TO WS-CLEARED-COUNT
               SUBTRACT WS-RETURN-AMOUNT FROM WS-CLEARED-AMOUNT
           ELSE
               ADD 1 TO WS-EXCEPTION-COUNT
               ADD WS-RETURN-AMOUNT TO WS-EXCEPTION-AMOUNT
           END-IF
           PERFORM WRITE-REPORT-ROW.

       WRITE-REPORT-ROW.
           MOVE SPACES TO REPORT-REC
           IF WS-MATCH-IDX > 0
               STRING WS-RETURN-DRAFT DELIMITED BY SIZE
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
               STRING WS-RETURN-DRAFT DELIMITED BY SIZE
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
