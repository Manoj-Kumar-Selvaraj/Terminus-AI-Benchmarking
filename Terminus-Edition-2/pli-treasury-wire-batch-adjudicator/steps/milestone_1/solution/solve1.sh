#!/bin/bash
set -euo pipefail
cat > /app/src/wire_batch.pli <<'EOF'
/* PL/I wire batch adjudicator control deck. */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE OFF
%SET CUTOFF_MODE OFF
%SET LEDGER_MODE OFF
%SET LIQUIDITY_MODE OFF
%SET SANCTIONS_MODE OFF
EOF
