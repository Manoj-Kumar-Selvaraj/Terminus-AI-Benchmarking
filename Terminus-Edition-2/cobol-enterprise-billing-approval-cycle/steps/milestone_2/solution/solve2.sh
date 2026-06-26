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

text = apply_m1(text)
text = apply_m2(text)
path.write_text(text)
PY
/app/scripts/run_batch.sh
