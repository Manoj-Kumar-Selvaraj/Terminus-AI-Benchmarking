#!/bin/bash
set -euo pipefail
cat > /app/src/posting_batch.pli <<'EOF'
/* PL/I general ledger posting normalizer control deck. */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
EOF
/app/scripts/run_batch.sh
