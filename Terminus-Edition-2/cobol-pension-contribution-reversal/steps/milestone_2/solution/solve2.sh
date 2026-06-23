#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
from pathlib import Path

path = Path("/app/src/pension_reversal_reconcile.cbl")
text = path.read_text()
old = """           MOVE ACT-CAT TO CANON-CAT
           MOVE "N" TO MATCHED-FLAG"""
new = """           MOVE ACT-CAT TO CANON-CAT
           IF ACT-CAT(1:2) = "EE"
               MOVE "EMP" TO CANON-CAT
           END-IF
           IF ACT-CAT(1:2) = "ER"
               MOVE "ERD" TO CANON-CAT
           END-IF
           IF ACT-CAT(1:2) = "VL"
               MOVE "VOL" TO CANON-CAT
           END-IF
           MOVE "N" TO MATCHED-FLAG"""
if new not in text:
    if old not in text:
        raise SystemExit("milestone 2 alias patch anchor missing")
    path.write_text(text.replace(old, new, 1))
PY

/app/scripts/run_batch.sh
