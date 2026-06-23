*> Fixed-block record layouts used by the FNBULKUP offline simulator.
       01  FINUPD-HEADER.
           05  HDR-REC-TYPE              PIC X.
           05  HDR-BATCH-ID              PIC X(10).
           05  HDR-BUSINESS-DATE         PIC 9(8).
           05  HDR-SOURCE                PIC X(8).
       01  FINUPD-DETAIL.
           05  DTL-REC-TYPE              PIC X.
           05  DTL-SEQUENCE              PIC 9(6).
           05  DTL-ACCOUNT-ID            PIC X(12).
           05  DTL-OP-CODE               PIC X(3).
           05  DTL-AMOUNT-SIGN           PIC X.
           05  DTL-AMOUNT-CENTS          PIC 9(12).
           05  DTL-GROUP-ID              PIC X(6).
           05  DTL-EVENT-ID              PIC X(8).
       01  FINUPD-TRAILER.
           05  TRL-REC-TYPE              PIC X.
           05  TRL-BATCH-ID              PIC X(10).
           05  TRL-DETAIL-COUNT          PIC 9(6).
           05  TRL-TOTAL-SIGN            PIC X.
           05  TRL-TOTAL-CENTS           PIC 9(12).
