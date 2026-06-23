#!/usr/bin/env bash
set -euo pipefail


cd /app

python3 <<'PY'
from pathlib import Path

path = Path("/app/cmd/reconcile/main.go")
text = path.read_text()

text = text.replace(
    "Method: strings.ToUpper(clean(row[4]))",
    "Method: canonicalMethod(row[4])",
)
text = text.replace(
    "Method: strings.ToUpper(clean(row[3]))",
    "Method: canonicalMethod(row[3])",
)
text = text.replace(
    'func clean(value string) string {\n\treturn strings.TrimSpace(value)\n}\n\nfunc allowedMethod(method string) bool {\n\tmethod = strings.ToUpper(clean(method))\n\treturn method == "DIRECT" || method == "PAYROLL" || method == "DEBIT"\n}',
    '''func clean(value string) string {
\treturn strings.TrimSpace(value)
}

func canonicalMethod(method string) string {
	switch strings.ToUpper(clean(method)) {
	case "ACH":
		return "DIRECT"
	case "PR":
		return "PAYROLL"
	case "DBT":
		return "DEBIT"
	default:
		return strings.ToUpper(clean(method))
	}
}

func allowedMethod(method string) bool {
\tmethod = canonicalMethod(method)
\treturn method == "DIRECT" || method == "PAYROLL" || method == "DEBIT"
}''',
)

path.write_text(text)
PY

/app/scripts/run_batch.sh
test -s /app/out/repayment_report.csv
test -s /app/out/repayment_summary.json
