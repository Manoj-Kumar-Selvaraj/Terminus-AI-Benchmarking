#!/usr/bin/env bash
set -euo pipefail
cd /app
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
if ! grep -q "MOVE WS-ACCOUNT-TOTAL TO WS-TIER-AMOUNT" /app/src/billing_approval.cbl; then
  bash "$STEPS_ROOT/milestone_1/solution/solve1.sh"
fi
python3 <<'PY'
from pathlib import Path
path = Path("/app/src/billing_approval.cbl")
text = path.read_text()
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
if old not in text:
    raise SystemExit("milestone 2 patch anchor missing")
path.write_text(text.replace(old, new, 1))
text = path.read_text()
old = """           IF WS-DUP-BATCH-FOUND = "Y"
               ADD 1 TO WS-DUP-BLOCKED
               MOVE "DUPBATCH" TO WS-FINAL-STATUS
               GO TO FINALIZE-RESET
           END-IF"""
new = """           IF WS-DUP-BATCH-FOUND = "Y"
               ADD 1 TO WS-DUP-BLOCKED
               MOVE "DUPBATCH" TO WS-FINAL-STATUS
               PERFORM FINALIZE-RESET
               GO TO FINALIZE-DONE
           END-IF"""
if old not in text:
    raise SystemExit("milestone 2 duplicate branch anchor missing")
text = text.replace(old, new, 1)
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
               PERFORM FINALIZE-RESET
               GO TO FINALIZE-DONE
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
if old not in text:
    raise SystemExit("milestone 2 finalize paragraph anchor missing")
path.write_text(text.replace(old, new, 1))
PY
/app/scripts/run_batch.sh
