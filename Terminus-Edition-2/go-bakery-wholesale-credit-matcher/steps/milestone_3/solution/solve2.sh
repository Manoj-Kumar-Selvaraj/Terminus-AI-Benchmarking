#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Route: strings.ToUpper(clean(row[4]))",
    "Route: canonicalRoute(row[4])",
)
text = text.replace(
    "Route: strings.ToUpper(clean(row[3]))",
    "Route: canonicalRoute(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedRoute(route string) bool {\n\troute = strings.ToUpper(clean(route))\n\treturn route == "LOCAL" || route == "REGIONAL" || route == "EXPORT"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalRoute(route string) string {
	switch strings.ToUpper(clean(route)) {
	case "LOC":
		return "LOCAL"
	case "REG":
		return "REGIONAL"
	case "EXP":
		return "EXPORT"
	default:
		return strings.ToUpper(clean(route))
	}
}

func allowedRoute(route string) bool {
\troute = canonicalRoute(route)
\treturn route == "LOCAL" || route == "REGIONAL" || route == "EXPORT"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
