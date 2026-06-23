#!/bin/bash
set -euo pipefail
cat > /app/src/tape_batch.pli <<'PLI'
/* mainframe tape record integrity auditor batch control deck */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
PLI
