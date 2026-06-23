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
path.write_text(text.replace(old, new, 1))
PY
/app/scripts/run_batch.sh
test -s /app/out/invoice_register.dat
