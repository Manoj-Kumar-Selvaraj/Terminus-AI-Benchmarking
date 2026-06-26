#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path
path = Path("/app/src/billing_approval.cbl")
text = path.read_text()
old = "           MOVE WS-LAST-LINE-AMOUNT TO WS-TIER-AMOUNT"
new = "           MOVE WS-ACCOUNT-TOTAL TO WS-TIER-AMOUNT"
if old not in text:
    raise SystemExit("milestone 1 patch anchor missing")
text = text.replace(old, new, 1)
old_add = "           ADD USG-AMOUNT TO WS-ACCOUNT-TOTAL"
new_add = """           IF USG-AMOUNT > 0
               ADD USG-AMOUNT TO WS-ACCOUNT-TOTAL
           END-IF"""
if old_add in text:
    text = text.replace(old_add, new_add, 1)
elif "IF USG-AMOUNT > 0" not in text:
    raise SystemExit("milestone 1 positive amount anchor missing")
path.write_text(text)
PY
/app/scripts/run_batch.sh
test -s /app/out/invoice_register.dat
