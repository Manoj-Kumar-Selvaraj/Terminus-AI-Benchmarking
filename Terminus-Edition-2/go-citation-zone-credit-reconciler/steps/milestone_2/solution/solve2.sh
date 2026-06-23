#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/solve1.sh" ] && ! grep -q 'func clean(value string)' /app/cmd/reconcile/main.go; then
  bash "$SCRIPT_DIR/solve1.sh"
fi

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Zone: strings.ToUpper(clean(row[4]))",
    "Zone: canonicalZone(row[4])",
)
text = text.replace(
    "Zone: strings.ToUpper(clean(row[3]))",
    "Zone: canonicalZone(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedZone(zone string) bool {\n\tzone = strings.ToUpper(clean(zone))\n\treturn zone == "STREET" || zone == "GARAGE" || zone == "LOT"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalZone(zone string) string {
	switch strings.ToUpper(clean(zone)) {
	case "ST":
		return "STREET"
	case "GRG":
		return "GARAGE"
	case "LT":
		return "LOT"
	default:
		return strings.ToUpper(clean(zone))
	}
}

func allowedZone(zone string) bool {
\tzone = canonicalZone(zone)
\treturn zone == "STREET" || zone == "GARAGE" || zone == "LOT"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
