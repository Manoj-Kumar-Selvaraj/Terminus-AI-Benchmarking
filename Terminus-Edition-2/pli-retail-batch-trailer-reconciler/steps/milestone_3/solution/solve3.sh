#!/bin/bash
set -euo pipefail
cat > /app/src/trailer_batch.pli <<'PLI'
/* retail batch trailer reconciler batch control deck */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
PLI
/app/scripts/run_batch.sh
