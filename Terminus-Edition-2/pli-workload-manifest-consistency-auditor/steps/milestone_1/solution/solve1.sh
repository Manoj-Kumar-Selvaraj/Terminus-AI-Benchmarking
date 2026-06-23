#!/bin/bash
set -euo pipefail
cat > /app/src/manifest_batch.pli <<'PLI'
/* workload manifest consistency auditor batch control deck */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
PLI
/app/scripts/run_batch.sh
