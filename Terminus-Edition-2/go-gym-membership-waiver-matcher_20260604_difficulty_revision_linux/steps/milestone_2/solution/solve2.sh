#!/usr/bin/env bash
set -euo pipefail

cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Plan: strings.ToUpper(clean(row[4]))",
    "Plan: canonicalPlan(row[4])",
)
text = text.replace(
    "Plan: strings.ToUpper(clean(row[3]))",
    "Plan: canonicalPlan(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedPlan(plan string) bool {\n\tplan = strings.ToUpper(clean(plan))\n\treturn plan == "BASIC" || plan == "PLUS" || plan == "ELITE"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalPlan(plan string) string {
	switch strings.ToUpper(clean(plan)) {
	case "BAS":
		return "BASIC"
	case "PLU":
		return "PLUS"
	case "ELI":
		return "ELITE"
	default:
		return strings.ToUpper(clean(plan))
	}
}

func allowedPlan(plan string) bool {
\tplan = canonicalPlan(plan)
\treturn plan == "BASIC" || plan == "PLUS" || plan == "ELITE"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/waiver_report.csv
test -s /app/out/waiver_summary.json
