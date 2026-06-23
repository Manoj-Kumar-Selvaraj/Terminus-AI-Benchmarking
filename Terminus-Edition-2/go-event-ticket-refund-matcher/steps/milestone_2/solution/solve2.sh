#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd /app

if grep -q 'func canonicalTier' /app/cmd/reconcile/main.go; then
  /app/scripts/run_batch.sh
  test -s /app/out/refund_report.csv
  test -s /app/out/refund_summary.json
  exit 0
fi

if ! grep -q 'usedBookings' /app/cmd/reconcile/main.go; then
  bash "$SCRIPT_DIR/solve1.sh"
fi

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Tier: strings.ToUpper(clean(row[4]))",
    "Tier: canonicalTier(row[4])",
)
text = text.replace(
    "Tier: strings.ToUpper(clean(row[3]))",
    "Tier: canonicalTier(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedTier(tier string) bool {\n\ttier = strings.ToUpper(clean(tier))\n\treturn tier == "GA" || tier == "VIP" || tier == "COMP"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalTier(tier string) string {
	switch strings.ToUpper(clean(tier)) {
	case "STD":
		return "GA"
	case "PLT":
		return "VIP"
	case "INV":
		return "COMP"
	default:
		return strings.ToUpper(clean(tier))
	}
}

func allowedTier(tier string) bool {
\ttier = canonicalTier(tier)
\treturn tier == "GA" || tier == "VIP" || tier == "COMP"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
