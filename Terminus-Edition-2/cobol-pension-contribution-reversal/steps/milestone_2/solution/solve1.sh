#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/pension_reversal_reconcile.cbl")
text = path.read_text()
old = """               IF ACT-ID = SRC-ID(I)
                  AND ACT-ACCT = SRC-ACCT(I)
                  AND CANON-CAT = SRC-CAT(I)
                  AND ACT-AMT = SRC-AMT(I)

                   MOVE "Y" TO MATCHED-FLAG
                   MOVE I TO MATCH-IDX
                   CONTINUE
               END-IF"""
new = """               IF ACT-ID = SRC-ID(I)
                  AND ACT-ACCT = SRC-ACCT(I)
                  AND CANON-CAT = SRC-CAT(I)
                  AND ACT-AMT = SRC-AMT(I)
                  AND SRC-BRANCH(I) = ACT-BRANCH
                  AND SRC-USED(I) NOT = "Y"
                  AND SRC-STATUS(I) = "P"
                  AND (SRC-CAT(I) = "EMP"
                    OR SRC-CAT(I) = "ERD"
                    OR SRC-CAT(I) = "VOL")
                  AND (ACT-REASON = "R02"
                    OR ACT-REASON = "R05"
                    OR ACT-REASON = "R14")
                  AND ACT-DATE IS NUMERIC
                  AND SRC-DATE(I) IS NUMERIC
                  AND ACT-DATE >= SRC-DATE(I)
                   MOVE "Y" TO MATCHED-FLAG
                   MOVE I TO MATCH-IDX
                   MOVE "Y" TO SRC-USED(I)
               END-IF"""
if new not in text:
    if old not in text:
        raise SystemExit("milestone 1 gate patch anchor missing")
    path.write_text(text.replace(old, new, 1))
PY

/app/scripts/run_batch.sh
