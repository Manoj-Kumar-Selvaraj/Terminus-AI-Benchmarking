       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARD-CLEAR.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT SALE-FILE ASSIGN TO "/app/data/sales.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CHGBK-FILE ASSIGN TO "/app/data/chargebacks.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT REPORT-FILE ASSIGN TO "/app/out/chargeback_report.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUMMARY-FILE ASSIGN TO "/app/out/chargeback_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD SALE-FILE.
       01 SALE-REC PIC X(64).
       FD CHGBK-FILE.
       01 CHGBK-REC PIC X(64).
       FD REPORT-FILE.
       01 REPORT-REC PIC X(160).
       FD SUMMARY-FILE.
       01 SUMMARY-REC PIC X(80).

       WORKING-STORAGE SECTION.
       01 WS-EOF-SALE PIC X VALUE "N".
       01 WS-EOF-CHGBK PIC X VALUE "N".
       01 WS-IDX PIC 9(4) COMP VALUE 0.
       01 WS-SALE-COUNT PIC 9(4) COMP VALUE 0.
       01 WS-MATCH-IDX PIC 9(4) COMP VALUE 0.
       01 WS-APPLIED-COUNT PIC 9(6) VALUE 0.
       01 WS-EXCEPTION-COUNT PIC 9(6) VALUE 0.
       01 WS-APPLIED-AMOUNT PIC S9(12) SIGN LEADING SEPARATE VALUE 0.
       01 WS-EXCEPTION-AMOUNT PIC 9(12) VALUE 0.
       01 WS-CHGBK-SALE PIC X(12).
       01 WS-CHGBK-AMOUNT PIC 9(10).
       01 WS-CHGBK-MERCHANT PIC X(8).
       01 WS-SALES.
          05 SALE-TABLE OCCURS 250 TIMES.
             10 SL-ID PIC X(12).
             10 SL-REASON PIC X(3).
             10 SL-AMOUNT PIC 9(10).
             10 SL-MERCHANT PIC X(8).
             10 SL-STATUS PIC X.

       PROCEDURE DIVISION.
       MAIN-PARA.
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

       STORE-SALE.
           ADD 1 TO WS-SALE-COUNT
           MOVE SALE-REC(2:12) TO SL-ID(WS-SALE-COUNT)
           MOVE SALE-REC(14:3) TO SL-REASON(WS-SALE-COUNT)
           MOVE SALE-REC(17:10) TO SL-AMOUNT(WS-SALE-COUNT)
           MOVE SALE-REC(27:8) TO SL-MERCHANT(WS-SALE-COUNT)
           MOVE SALE-REC(35:1) TO SL-STATUS(WS-SALE-COUNT).

       PROCESS-CHARGEBACK.
           MOVE CHGBK-REC(2:12) TO WS-CHGBK-SALE
           MOVE CHGBK-REC(14:10) TO WS-CHGBK-AMOUNT
           MOVE CHGBK-REC(24:8) TO WS-CHGBK-MERCHANT
           MOVE 0 TO WS-MATCH-IDX
           PERFORM VARYING WS-IDX FROM 1 BY 1
               UNTIL WS-IDX > WS-SALE-COUNT OR WS-MATCH-IDX > 0
               IF SL-ID(WS-IDX)(1:10) = WS-CHGBK-SALE(1:10)
                  AND SL-MERCHANT(WS-IDX) = WS-CHGBK-MERCHANT
                  AND SL-AMOUNT(WS-IDX) = WS-CHGBK-AMOUNT
                  AND SL-STATUS(WS-IDX) = "S"
                  AND (SL-REASON(WS-IDX) = "F10"
                       OR SL-REASON(WS-IDX) = "F20"
                       OR SL-REASON(WS-IDX) = "R99")
                   MOVE WS-IDX TO WS-MATCH-IDX
               END-IF
           END-PERFORM

           IF WS-MATCH-IDX > 0
               ADD 1 TO WS-APPLIED-COUNT
               SUBTRACT WS-CHGBK-AMOUNT FROM WS-APPLIED-AMOUNT
           ELSE
               ADD 1 TO WS-EXCEPTION-COUNT
               ADD WS-CHGBK-AMOUNT TO WS-EXCEPTION-AMOUNT
           END-IF
           PERFORM WRITE-REPORT-ROW.

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
