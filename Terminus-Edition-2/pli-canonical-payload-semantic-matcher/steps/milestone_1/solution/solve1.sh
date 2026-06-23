#!/bin/bash
set -euo pipefail
cat > /app/src/semantic_batch.pli <<'PLI'
/* canonical payload semantic matcher batch control deck */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
PLI
/app/scripts/run_batch.sh
