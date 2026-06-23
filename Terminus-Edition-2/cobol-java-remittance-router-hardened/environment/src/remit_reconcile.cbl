       IDENTIFICATION DIVISION.
       PROGRAM-ID. REMIT-RECON.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT REMIT-FILE ASSIGN TO "/app/data/remittances.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT EXPORT-FILE ASSIGN TO "/app/out/remit_export.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUMMARY-FILE ASSIGN TO "/app/out/remit_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD REMIT-FILE.
       01 REMIT-REC PIC X(80).
       FD EXPORT-FILE.
       01 EXPORT-REC PIC X(160).
       FD SUMMARY-FILE.
       01 SUMMARY-REC PIC X(80).

       WORKING-STORAGE SECTION.
       01 WS-EOF PIC X VALUE "N".
       01 WS-EXPORTED-COUNT PIC 9(6) VALUE 0.
       01 WS-EXPORTED-AMOUNT PIC S9(12) SIGN LEADING SEPARATE VALUE 0.
       01 WS-REJECTED-COUNT PIC 9(6) VALUE 0.
       01 WS-TXN-ID PIC X(12).
       01 WS-ACCOUNT PIC X(8).
       01 WS-RAIL PIC X(3).
       01 WS-AMOUNT PIC 9(10).
       01 WS-DATE PIC X(8).
       01 WS-STATUS PIC X.

       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN INPUT REMIT-FILE
           OPEN OUTPUT EXPORT-FILE
           OPEN OUTPUT SUMMARY-FILE
           MOVE "transaction_id,account_id,rail,amount_cents,business_date" TO EXPORT-REC
           WRITE EXPORT-REC

           PERFORM UNTIL WS-EOF = "Y"
               READ REMIT-FILE
                   AT END
                       MOVE "Y" TO WS-EOF
                   NOT AT END
                       PERFORM PROCESS-REMIT
               END-READ
           END-PERFORM

           PERFORM WRITE-SUMMARY
           CLOSE REMIT-FILE
           CLOSE EXPORT-FILE
           CLOSE SUMMARY-FILE
           STOP RUN.

       PROCESS-REMIT.
           MOVE REMIT-REC(2:12) TO WS-TXN-ID
           MOVE REMIT-REC(14:8) TO WS-ACCOUNT
           MOVE REMIT-REC(22:3) TO WS-RAIL
           MOVE REMIT-REC(25:10) TO WS-AMOUNT
           MOVE REMIT-REC(35:8) TO WS-DATE
           MOVE REMIT-REC(43:1) TO WS-STATUS
           IF WS-STATUS = "P"
              AND (WS-RAIL = "ACH" OR WS-RAIL = "WIR")
               ADD 1 TO WS-EXPORTED-COUNT
               SUBTRACT WS-AMOUNT FROM WS-EXPORTED-AMOUNT
               MOVE SPACES TO EXPORT-REC
               STRING
                   WS-TXN-ID DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-ACCOUNT DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-RAIL DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-AMOUNT DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-DATE DELIMITED BY SIZE
                   INTO EXPORT-REC
               END-STRING
               WRITE EXPORT-REC
           ELSE
               ADD 1 TO WS-REJECTED-COUNT
           END-IF.

       WRITE-SUMMARY.
           MOVE SPACES TO SUMMARY-REC
           STRING "exported_count=" DELIMITED BY SIZE
               WS-EXPORTED-COUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "exported_amount_cents=" DELIMITED BY SIZE
               WS-EXPORTED-AMOUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "rejected_count=" DELIMITED BY SIZE
               WS-REJECTED-COUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC.