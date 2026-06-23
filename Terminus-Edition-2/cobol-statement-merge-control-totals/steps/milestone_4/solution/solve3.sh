#!/usr/bin/env bash
set -euo pipefail
cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/stmt_merge.cbl")
text = path.read_text()

commit_old = """       COMMIT-PENDING-GROUP.
           IF WS-PENDING-COUNT = 0
               GO TO COMMIT-DONE
           END-IF
           IF WS-FLUSH-ACCOUNT NOT = SPACES
               MOVE WS-FLUSH-ACCOUNT TO CTL-ACCOUNT
               MOVE WS-FLUSH-DATE TO CTL-STMT-DATE
           ELSE
               MOVE WS-PENDING-ACCOUNT TO CTL-ACCOUNT
               MOVE WS-PENDING-DATE TO CTL-STMT-DATE
           END-IF"""

commit_new = """       COMMIT-PENDING-GROUP.
           IF WS-PENDING-COUNT = 0
               GO TO COMMIT-DONE
           END-IF
           MOVE WS-PENDING-ACCOUNT TO CTL-ACCOUNT
           MOVE WS-PENDING-DATE TO CTL-STMT-DATE"""

if commit_old in text:
    text = text.replace(commit_old, commit_new, 1)

if "MOVE SPACES TO WS-FLUSH-ACCOUNT" in text:
    text = text.replace("           MOVE SPACES TO WS-FLUSH-ACCOUNT\n", "", 1)
    text = text.replace("           MOVE SPACES TO WS-FLUSH-DATE\n", "", 1)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/control_totals.dat
