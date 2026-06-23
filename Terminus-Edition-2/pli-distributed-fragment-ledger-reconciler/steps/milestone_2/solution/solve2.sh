#!/bin/bash
set -euo pipefail
cat > /app/src/fragment_batch.pli <<'EOF'
/* PL/I fragment ledger reconciler control deck. */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE OFF
%SET DUP_MODE SKIP
EOF
/app/scripts/run_batch.sh
