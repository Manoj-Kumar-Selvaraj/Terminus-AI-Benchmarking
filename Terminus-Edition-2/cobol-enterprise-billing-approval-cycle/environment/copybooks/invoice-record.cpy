       *> Invoice output (72 bytes)
       01 INV-OUT-REC-DATA.
          05 INV-TYPE           PIC X.
          05 INV-ACCOUNT        PIC X(8).
          05 INV-NUMBER         PIC 9(10).
          05 INV-TOTAL          PIC S9(10).
          05 INV-TIER           PIC X(10).
          05 INV-STAGES         PIC X(16).
          05 INV-STATUS         PIC X(8).
          05 INV-FILLER         PIC X(9).
       01 INV-OUT-BUF REDEFINES INV-OUT-REC-DATA PIC X(72).
