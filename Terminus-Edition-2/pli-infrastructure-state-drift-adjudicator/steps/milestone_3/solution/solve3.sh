#!/bin/bash
set -euo pipefail
cat > /app/src/drift_batch.pli <<'PLI'
/* infrastructure state drift adjudicator batch control deck */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
PLI
/app/scripts/run_batch.sh
