#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd /app

# Milestone 3 placeholder: extend with calendar, tie-break, or config loading.
# Until you add M3 logic, ensure prior milestones are applied on a fresh container.
if ! grep -q 'func canonicalTier' /app/cmd/reconcile/main.go; then
  bash "$SCRIPT_DIR/solve1.sh"
  bash "$SCRIPT_DIR/solve2.sh"
fi

if ! grep -q 'TEMPLATE_M3_MARKER' /app/cmd/reconcile/main.go; then
  python3 <<'PY'
from pathlib import Path
path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()
if "TEMPLATE_M3_MARKER" not in text:
    text = text.replace("package main", "package main\n\n// TEMPLATE_M3_MARKER: add milestone 3 behavior here.")
    path.write_text(text)
PY
fi

/app/scripts/run_batch.sh
test -s /app/out/template_report.csv
test -s /app/out/template_summary.json
