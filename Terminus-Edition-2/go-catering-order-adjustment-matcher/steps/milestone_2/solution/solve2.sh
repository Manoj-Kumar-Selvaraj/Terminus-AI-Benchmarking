#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEPS_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Service: strings.ToUpper(clean(row[4]))",
    "Service: canonicalService(row[4])",
)
text = text.replace(
    "Service: strings.ToUpper(clean(row[3]))",
    "Service: canonicalService(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedService(service string) bool {\n\tservice = strings.ToUpper(clean(service))\n\treturn service == "PICKUP" || service == "DELIVERY" || service == "ONSITE"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalService(service string) string {
	switch strings.ToUpper(clean(service)) {
	case "PU":
		return "PICKUP"
	case "DEL":
		return "DELIVERY"
	case "OS":
		return "ONSITE"
	default:
		return strings.ToUpper(clean(service))
	}
}

func allowedService(service string) bool {
\tservice = canonicalService(service)
\treturn service == "PICKUP" || service == "DELIVERY" || service == "ONSITE"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/adjustment_report.csv
test -s /app/out/adjustment_summary.json
