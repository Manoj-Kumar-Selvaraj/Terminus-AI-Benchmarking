#!/bin/bash
set -euo pipefail
cat > /app/src/wire_batch.pli <<'EOF'
/* PL/I wire batch adjudicator control deck. */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
%SET CUTOFF_MODE ON
%SET LEDGER_MODE ON
%SET LIQUIDITY_MODE ON
%SET SANCTIONS_MODE ON
EOF
