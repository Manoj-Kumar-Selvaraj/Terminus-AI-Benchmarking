#!/bin/bash
set -euo pipefail
cat > /app/src/ledger_batch.pli <<'PLI'
/* multicurrency ledger clearing processor batch control deck */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE OFF
PLI
