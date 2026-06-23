#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cat > /app/src/audit_batch.pli <<'EOF'
/* PL/I batch control deck for orbit downlink frame auditor. */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
EOF
install -m 0755 "$SCRIPT_DIR/downlink_audit.py" /app/scripts/downlink_audit.py
cat > /app/scripts/run_batch.sh <<'EOF'
#!/bin/bash
set -euo pipefail
python3 /app/scripts/downlink_audit.py
EOF
chmod +x /app/scripts/run_batch.sh
/app/scripts/run_batch.sh
