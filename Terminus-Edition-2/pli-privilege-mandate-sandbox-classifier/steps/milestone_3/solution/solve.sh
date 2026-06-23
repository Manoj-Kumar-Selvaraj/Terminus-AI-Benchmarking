#!/bin/bash
set -euo pipefail
cat > /app/src/mandate_batch.pli <<'PLI'
/* privilege mandate sandbox classifier batch control deck */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
PLI
