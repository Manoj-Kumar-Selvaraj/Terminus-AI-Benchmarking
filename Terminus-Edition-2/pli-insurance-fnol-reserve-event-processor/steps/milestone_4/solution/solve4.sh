#!/bin/bash
set -euo pipefail
cat > /app/src/fnol_batch.pli <<'EOF'
/* PL/I insurance FNOL reserve batch control deck. */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
%SET LEDGER_MODE ON
%SET LIMIT_MODE ON
%SET SUBROGATION_MODE ON
EOF
