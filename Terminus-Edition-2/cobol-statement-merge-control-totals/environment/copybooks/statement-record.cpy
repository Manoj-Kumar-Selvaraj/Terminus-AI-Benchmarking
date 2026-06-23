      * Statement stream input record (48 bytes)
       01 STM-IN-REC.
          05 STM-TYPE           PIC X.
          05 STM-ACCOUNT        PIC X(8).
          05 STM-STMT-DATE      PIC X(8).
          05 STM-SEQ            PIC X(5).
          05 STM-TXN-TYPE       PIC X(2).
          05 STM-AMOUNT         PIC 9(10).
          05 STM-STREAM-TAG     PIC X(14).
       01 STM-COMPOSITE-KEY     PIC X(21).
       01 STM-GROUP-KEY         PIC X(16).
