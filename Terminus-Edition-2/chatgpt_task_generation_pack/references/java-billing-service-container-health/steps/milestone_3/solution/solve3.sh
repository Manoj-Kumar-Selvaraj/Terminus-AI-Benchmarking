#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash /steps/milestone_2/solution/solve2.sh
cat > /app/config/jvm.options <<'EOF'
-XX:+UseContainerSupport
-XX:MaxRAMPercentage=70.0
EOF
