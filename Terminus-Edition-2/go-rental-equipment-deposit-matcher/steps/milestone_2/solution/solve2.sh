#!/usr/bin/env bash
set -euo pipefail


cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Depot: strings.ToUpper(clean(row[4]))",
    "Depot: canonicalDepot(row[4])",
)
text = text.replace(
    "Depot: strings.ToUpper(clean(row[3]))",
    "Depot: canonicalDepot(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedDepot(depot string) bool {\n\tdepot = strings.ToUpper(clean(depot))\n\treturn depot == "YARD" || depot == "DELIVERY" || depot == "PICKUP"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalDepot(depot string) string {
	switch strings.ToUpper(clean(depot)) {
	case "YD":
		return "YARD"
	case "DEL":
		return "DELIVERY"
	case "PU":
		return "PICKUP"
	default:
		return strings.ToUpper(clean(depot))
	}
}

func allowedDepot(depot string) bool {
\tdepot = canonicalDepot(depot)
\treturn depot == "YARD" || depot == "DELIVERY" || depot == "PICKUP"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/deposit_report.csv
test -s /app/out/deposit_summary.json
