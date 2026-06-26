#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
python3 <<'PY'
from pathlib import Path

path = Path("/app/src/billing_approval.cbl")
text = path.read_text()

def apply_m1(src: str) -> str:
    if "MOVE WS-LAST-LINE-AMOUNT TO WS-TIER-AMOUNT" in src:
        src = src.replace(
            "           MOVE WS-LAST-LINE-AMOUNT TO WS-TIER-AMOUNT",
            "           MOVE WS-ACCOUNT-TOTAL TO WS-TIER-AMOUNT",
            1,
        )
    elif "MOVE WS-ACCOUNT-TOTAL TO WS-TIER-AMOUNT" not in src:
        raise SystemExit("m1 tier anchor missing")
    old_add = "           ADD USG-AMOUNT TO WS-ACCOUNT-TOTAL"
    new_add = """           IF USG-AMOUNT > 0
               ADD USG-AMOUNT TO WS-ACCOUNT-TOTAL
           END-IF"""
    if old_add in src:
        src = src.replace(old_add, new_add, 1)
    elif "IF USG-AMOUNT > 0" not in src:
        raise SystemExit("m1 positive amount anchor missing")
    return src

def apply_m2(src: str) -> str:
    old = """       CHECK-PRIOR-LEDGER.
           MOVE "N" TO WS-DUP-BATCH-FOUND."""
    new = """       CHECK-PRIOR-LEDGER.
           MOVE "N" TO WS-DUP-BATCH-FOUND
           OPEN INPUT LEDGER-FILE
           PERFORM UNTIL WS-EOF-MAN = "Y"
               READ LEDGER-FILE AT END MOVE "Y" TO WS-EOF-MAN
               NOT AT END
                   IF LEDGER-LINE(1:1) = "P"
                       IF LEDGER-LINE(2:8) = WS-CURRENT-ACCOUNT
                           PERFORM VARYING WS-BATCH-IDX FROM 1 BY 1
                               UNTIL WS-BATCH-IDX > WS-BATCH-COUNT
                               IF LEDGER-LINE(10:6) =
                                      WS-BATCH-ENTRY(WS-BATCH-IDX)
                                   MOVE "Y" TO WS-DUP-BATCH-FOUND
                               END-IF
                           END-PERFORM
                       END-IF
                   END-IF
               END-READ
           END-PERFORM
           CLOSE LEDGER-FILE
           MOVE "N" TO WS-EOF-MAN."""
    if old in src:
        src = src.replace(old, new, 1)
    elif "OPEN INPUT LEDGER-FILE" not in src:
        raise SystemExit("m2 ledger anchor missing")
    old = """       FINALIZE-ACCOUNT.
           IF WS-USAGE-COUNT = 0
               GO TO FINALIZE-DONE
           END-IF
           PERFORM LOOKUP-ACCOUNT-STATUS
           IF WS-ACCOUNT-STATUS = "CLOSED"
               MOVE "HOLD" TO WS-FINAL-STATUS
               MOVE "CLOSED" TO WS-APPROVAL-TIER
               MOVE "CLOSED" TO WS-STAGE-TRACE
               GO TO FINALIZE-WRITE
           END-IF
           PERFORM CHECK-PRIOR-LEDGER
           IF WS-DUP-BATCH-FOUND = "Y"
               ADD 1 TO WS-DUP-BLOCKED
               MOVE "DUPBATCH" TO WS-FINAL-STATUS
               GO TO FINALIZE-RESET
           END-IF
           PERFORM DETERMINE-APPROVAL-TIER
           PERFORM RUN-APPROVAL-CHAIN
           PERFORM FINALIZE-WRITE
           ."""
    new = """       FINALIZE-ACCOUNT.
           IF WS-USAGE-COUNT > 0
               PERFORM LOOKUP-ACCOUNT-STATUS
               IF WS-ACCOUNT-STATUS = "CLOSED"
                   MOVE "HOLD" TO WS-FINAL-STATUS
                   MOVE "CLOSED" TO WS-APPROVAL-TIER
                   MOVE "CLOSED" TO WS-STAGE-TRACE
                   PERFORM FINALIZE-WRITE
               ELSE
                   PERFORM CHECK-PRIOR-LEDGER
                   IF WS-DUP-BATCH-FOUND = "Y"
                       ADD 1 TO WS-DUP-BLOCKED
                       MOVE "DUPBATCH" TO WS-FINAL-STATUS
                       PERFORM FINALIZE-RESET
                   ELSE
                       PERFORM DETERMINE-APPROVAL-TIER
                       PERFORM RUN-APPROVAL-CHAIN
                       PERFORM FINALIZE-WRITE
                   END-IF
               END-IF
           END-IF
           ."""
    if old in src:
        src = src.replace(old, new, 1)
    elif "IF WS-USAGE-COUNT > 0" not in src:
        raise SystemExit("m2 finalize anchor missing")
    return src

def apply_m3(src: str) -> str:
    old = """                       IF WS-APPROVAL-TIER = "DUAL"
                           PERFORM WRITE-TRACE-REGIONAL
                           MOVE "REGIONAL" TO WS-STAGE-TRACE
                           MOVE "APPROVED" TO WS-FINAL-STATUS
                       END-IF"""
    new = """                       IF WS-APPROVAL-TIER = "DUAL"
                           PERFORM WRITE-TRACE-REGIONAL
                           PERFORM WRITE-TRACE-FINANCE
                           MOVE "REGIONAL+FINANCE" TO WS-STAGE-TRACE
                           MOVE "APPROVED" TO WS-FINAL-STATUS
                       END-IF"""
    if old in src:
        src = src.replace(old, new, 1)
    elif 'MOVE "REGIONAL+FINANCE" TO WS-STAGE-TRACE' not in src:
        raise SystemExit("m3 dual anchor missing")
    return src

def apply_m4(src: str) -> str:
    old = """               MOVE WS-MAN-IDX TO WS-CURRENT-FILE-NUM
               MOVE WS-MAN-ENTRY(WS-MAN-IDX) TO WS-USG-PATH"""
    new = """               MOVE WS-MAN-IDX TO WS-CURRENT-FILE-NUM
               MOVE ZERO TO WS-FILE-RECORD-NUM
               MOVE WS-MAN-ENTRY(WS-MAN-IDX) TO WS-USG-PATH"""
    if old in src:
        src = src.replace(old, new, 1)
    elif "MOVE ZERO TO WS-FILE-RECORD-NUM" not in src:
        raise SystemExit("m4 file cursor anchor missing")
    start = src.index("       WRITE-CHECKPOINT.")
    end = src.index("       WRITE-SUMMARY.")
    new_checkpoint = """       WRITE-CHECKPOINT.
           OPEN OUTPUT CHECKPOINT-FILE
           MOVE SPACES TO WS-CKPT-REC
           MOVE WS-CURRENT-FILE-NUM TO WS-CKPT-REC(1:2)
           MOVE WS-FILE-RECORD-NUM TO WS-CKPT-REC(3:6)
           MOVE WS-CURRENT-ACCOUNT TO WS-CKPT-REC(9:8)
           MOVE WS-ACCOUNT-TOTAL TO WS-CKPT-REC(17:10)
           MOVE WS-USAGE-COUNT TO WS-CKPT-REC(27:6)
           MOVE WS-INVOICE-COUNTER TO WS-CKPT-REC(33:10)
           MOVE WS-ROW-COUNT TO WS-CKPT-REC(43:6)
           MOVE WS-TOTAL-USAGE-ROWS TO WS-CKPT-REC(49:6)
           MOVE WS-INVOICES-POSTED TO WS-CKPT-REC(55:6)
           MOVE WS-TOTAL-BILLED TO WS-CKPT-REC(61:12)
           MOVE WS-DUP-BLOCKED TO WS-CKPT-REC(73:6)
           MOVE WS-BATCH-COUNT TO WS-CKPT-REC(79:2)
           MOVE WS-LAST-LINE-AMOUNT TO WS-CKPT-REC(81:10)
           MOVE WS-BATCH-ENTRY(1) TO WS-CKPT-REC(91:6)
           MOVE WS-BATCH-ENTRY(2) TO WS-CKPT-REC(97:6)
           MOVE WS-BATCH-ENTRY(3) TO WS-CKPT-REC(103:6)
           MOVE WS-BATCH-ENTRY(4) TO WS-CKPT-REC(109:6)
           MOVE WS-BATCH-ENTRY(5) TO WS-CKPT-REC(115:6)
           MOVE WS-BATCH-ENTRY(6) TO WS-CKPT-REC(121:6)
           MOVE WS-BATCH-ENTRY(7) TO WS-CKPT-REC(127:6)
           MOVE WS-BATCH-ENTRY(8) TO WS-CKPT-REC(133:6)
           WRITE WS-CKPT-REC
           CLOSE CHECKPOINT-FILE
           ADD 1 TO WS-CHECKPOINT-COMMITS.

       LOAD-CHECKPOINT.
           OPEN INPUT CHECKPOINT-FILE
           READ CHECKPOINT-FILE
               AT END MOVE "N" TO WS-RESTART-FLAG
                   STOP RUN 1
               NOT AT END
                   PERFORM PARSE-CHECKPOINT-LINE
                   MOVE "Y" TO WS-RESTART-ACTIVE
           END-READ
           CLOSE CHECKPOINT-FILE.

       PARSE-CHECKPOINT-LINE.
           MOVE WS-CKPT-REC(1:2) TO WS-CKPT-FILE-NUM
           MOVE WS-CKPT-REC(3:6) TO WS-CKPT-RECORD-NUM
           MOVE WS-CKPT-REC(9:8) TO WS-CURRENT-ACCOUNT
           MOVE WS-CKPT-REC(17:10) TO WS-ACCOUNT-TOTAL
           MOVE WS-CKPT-REC(27:6) TO WS-USAGE-COUNT
           MOVE WS-CKPT-REC(33:10) TO WS-INVOICE-COUNTER
           MOVE WS-CKPT-REC(43:6) TO WS-ROW-COUNT
           MOVE WS-CKPT-REC(49:6) TO WS-TOTAL-USAGE-ROWS
           MOVE WS-CKPT-REC(55:6) TO WS-INVOICES-POSTED
           MOVE WS-CKPT-REC(61:12) TO WS-TOTAL-BILLED
           MOVE WS-CKPT-REC(73:6) TO WS-DUP-BLOCKED
           MOVE WS-CKPT-REC(79:2) TO WS-BATCH-COUNT
           MOVE WS-CKPT-REC(81:10) TO WS-LAST-LINE-AMOUNT
           MOVE WS-CKPT-REC(91:6) TO WS-BATCH-ENTRY(1)
           MOVE WS-CKPT-REC(97:6) TO WS-BATCH-ENTRY(2)
           MOVE WS-CKPT-REC(103:6) TO WS-BATCH-ENTRY(3)
           MOVE WS-CKPT-REC(109:6) TO WS-BATCH-ENTRY(4)
           MOVE WS-CKPT-REC(115:6) TO WS-BATCH-ENTRY(5)
           MOVE WS-CKPT-REC(121:6) TO WS-BATCH-ENTRY(6)
           MOVE WS-CKPT-REC(127:6) TO WS-BATCH-ENTRY(7)
           MOVE WS-CKPT-REC(133:6) TO WS-BATCH-ENTRY(8)
           .

"""
    if "MOVE WS-CURRENT-FILE-NUM TO WS-CKPT-REC(1:2)" not in src and 'STRING "file_num="' in src:
        start = src.index("       WRITE-CHECKPOINT.")
        end = src.index("       WRITE-SUMMARY.")
        src = src[:start] + new_checkpoint + src[end:]
    elif "MOVE WS-CURRENT-FILE-NUM TO WS-CKPT-REC(1:2)" not in src:
        raise SystemExit("m4 checkpoint anchor missing")
    return src

text = apply_m1(text)
text = apply_m2(text)
text = apply_m3(text)
text = apply_m4(text)
path.write_text(text)
PY
/app/scripts/run_batch.sh
